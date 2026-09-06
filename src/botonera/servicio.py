"""El servicio: vigila el teclado y le graba lo que dice la configuración.

Como el teclado no se puede leer, el servicio no «compara y corrige» como
hacen MiniMic y SikaiMini: **graba entero**. Al verlo por cable (si
``escribir_al_conectar`` está encendido) le manda los tres perfiles con sus
21 piezas y sus luces; cada cambio desde el panel graba la pieza o las luces
tocadas en el momento, y guarda la configuración, que es la única copia de
lo que el teclado tiene.

No hay dictado ni micrófono aquí: este teclado no los tiene. Para abrir el
dictado de los otros servicios basta con ponerle a una tecla su combinación
(``ctrl-mayus-alt-f13`` TecladoIA, ``f14`` MiniMic, ``f15`` SikaiMini).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tecladoia.sucesos import Bus

from . import __version__, dispositivo, escucha, protocolo
from .config import Ajustes, Perfil
from .protocolo import ErrorProtocolo, Luces

registro = logging.getLogger("botonera.servicio")


@dataclass
class Estado:
    presencia: dispositivo.Presencia = field(default_factory=dispositivo.Presencia)
    escribiendo: bool = False
    escuchando: bool = False
    ultima_escritura: str = ""
    mensajes_escritos: int = 0
    avisos: list[str] = field(default_factory=list)


class Servicio:
    def __init__(self, ajustes: Ajustes, teclado: dispositivo.Teclado | None = None) -> None:
        self.ajustes = ajustes
        self.teclado = teclado or dispositivo.Teclado()
        self.estado = Estado(ultima_escritura=ajustes.ultima_escritura)
        self.bus = Bus()
        self.bucle: asyncio.AbstractEventLoop | None = None
        self._parar = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._cerrojo = threading.Lock()

    # --- arranque y parada ------------------------------------------------

    async def arrancar(self) -> None:
        self.bucle = asyncio.get_running_loop()
        self._hilos.append(dispositivo.vigilar_presencia(self._al_cambiar_presencia, parar=self._parar))
        registro.info("Botonera %s en marcha", __version__)

    async def detener(self) -> None:
        self._parar.set()

    # --- lo que ve el panel ---------------------------------------------------

    def resumen(self) -> dict[str, Any]:
        e = self.estado
        p = e.presencia
        return {
            "version": __version__,
            "conexion": {
                "cable": p.cable, "bluetooth": p.bluetooth, "conectado": p.conectado,
                "configurable": p.configurable, "descripcion": p.descripcion,
                "otro_jieli": p.otro_jieli, "serie": p.serie,
            },
            "perfiles": [perfil.como_dict() for perfil in self.ajustes.todos_los_perfiles()],
            "piezas": list(protocolo.NOMBRES_DE_LAS_PIEZAS),
            "gestos": list(protocolo.GESTOS),
            "filas": protocolo.FILAS, "columnas": protocolo.COLUMNAS,
            "escribir_al_conectar": self.ajustes.escribir_al_conectar,
            "ultima_escritura": e.ultima_escritura,
            "mensajes_escritos": e.mensajes_escritos,
            "escribiendo": e.escribiendo,
            "escuchando": e.escuchando,
            "modos_de_luz": [{"valor": v, "nombre": n} for v, n in protocolo.MODOS_DE_LUZ.items()],
            "avisos": list(e.avisos),
        }

    def publicar(self, tipo: str, datos: dict[str, Any] | None = None) -> None:
        if self.bucle is None:
            return
        carga = datos if datos is not None else self.resumen()
        try:
            self.bucle.call_soon_threadsafe(self.bus.publicar, tipo, carga)
        except RuntimeError:
            pass

    def _avisar(self, texto: str) -> None:
        registro.warning(texto)
        with self._cerrojo:
            self.estado.avisos = ([texto] + self.estado.avisos)[:5]

    # --- presencia -----------------------------------------------------------

    def _al_cambiar_presencia(self, presencia: dispositivo.Presencia) -> None:
        self.estado.presencia = presencia
        registro.info("teclado: %s", presencia.descripcion)
        if presencia.configurable and self.ajustes.escribir_al_conectar:
            time.sleep(1.0)  # Windows termina de montar las interfaces
            try:
                r = self.aplicar()
                registro.info("grabados los tres perfiles al conectar (%s mensajes)", r.get("mensajes"))
            except (dispositivo.ErrorDispositivo, ErrorProtocolo) as e:
                self._avisar(f"no se pudo grabar el teclado al conectarlo: {e}")
        self.publicar("estado")

    # --- escribir ------------------------------------------------------------------

    def _escribir(self, mensajes: list[bytes]) -> int:
        self.estado.escribiendo = True
        self.publicar("estado")
        try:
            n = self.teclado.escribir(mensajes)
        finally:
            self.estado.escribiendo = False
        self.estado.mensajes_escritos += n
        self.estado.ultima_escritura = datetime.now().isoformat(timespec="seconds")
        self.ajustes.ultima_escritura = self.estado.ultima_escritura
        if self.estado.presencia.serie:
            self.ajustes.serie_del_teclado = self.estado.presencia.serie
        try:
            self.ajustes.guardar()
        except OSError as e:
            registro.warning("no se pudo guardar la configuración: %s", e)
        return n

    def _sin_cable(self, **extra: Any) -> dict[str, Any]:
        motivo = "el teclado Jieli que hay por cable es otro (MiniMic o SiKai)" if self.estado.presencia.otro_jieli else "se grabará cuando el teclado esté por cable"
        return {"escrito": False, "aviso": f"guardado; {motivo}", **extra}

    def aplicar(self, perfil: int | None = None) -> dict[str, Any]:
        """Graba los tres perfiles (o uno) tal como están en la configuración."""
        indices = [perfil] if perfil is not None else list(range(protocolo.NUMERO_DE_PERFILES))
        mensajes: list[bytes] = []
        for i in indices:
            p = self.ajustes.perfil(i)
            mensajes.extend(protocolo.mensajes_de_perfil(i, p.acciones(), p.luces()))
        if not self.estado.presencia.configurable:
            return self._sin_cable(mensajes=len(mensajes))
        n = self._escribir(mensajes)
        self.publicar("estado")
        return {"escrito": True, "mensajes": n, "perfiles": indices, "ultima_escritura": self.estado.ultima_escritura}

    def poner_pieza(self, perfil: int, pieza: int, texto: str) -> dict[str, Any]:
        """Guarda lo que hace una pieza y, si el teclado está por cable, se lo graba."""
        p = self.ajustes.perfil(perfil)
        accion = p.poner_pieza(pieza, texto)  # ErrorProtocolo -> 400
        self.ajustes.guardar_perfil(perfil, p)
        self.ajustes.guardar()
        if not self.estado.presencia.configurable:
            self.publicar("estado")
            return self._sin_cable(accion=str(accion))
        self._escribir(protocolo.mensajes_de_pieza(perfil, pieza, accion))
        self.publicar("estado")
        return {"escrito": True, "accion": str(accion), "pieza": pieza, "perfil": perfil}

    def poner_perfil(self, perfil: int, datos: dict[str, Any]) -> dict[str, Any]:
        """Cambia lo que se pida de un perfil (nombre, teclas, perillas, luces) y lo graba entero."""
        actual = self.ajustes.perfil(perfil)
        nuevo = Perfil.desde_dict({**actual.como_dict(), **datos}, perfil)
        if "teclas" in datos and (not isinstance(datos["teclas"], list) or len(datos["teclas"]) != protocolo.NUMERO_DE_TECLAS):
            raise ValueError(f"«teclas» tiene que ser una lista de {protocolo.NUMERO_DE_TECLAS} textos")
        if "perillas" in datos and (not isinstance(datos["perillas"], list) or len(datos["perillas"]) != protocolo.NUMERO_DE_PERILLAS):
            raise ValueError(f"«perillas» tiene que ser una lista de {protocolo.NUMERO_DE_PERILLAS} listas de 3 textos")
        if "luces_modo" in datos and (not isinstance(datos["luces_modo"], int) or isinstance(datos["luces_modo"], bool) or not 0 <= datos["luces_modo"] <= 255):
            raise ValueError("«luces_modo» va de 0 a 255")
        if "luces_color" in datos:
            protocolo.color_desde_texto(str(datos["luces_color"]))  # ErrorProtocolo -> 400
        self.ajustes.guardar_perfil(perfil, nuevo)  # normaliza; ErrorProtocolo si algo está mal escrito
        self.ajustes.guardar()
        if not self.estado.presencia.configurable:
            self.publicar("estado")
            return self._sin_cable(perfil=self.ajustes.perfil(perfil).como_dict())
        r = self.aplicar(perfil)
        r["perfil"] = self.ajustes.perfil(perfil).como_dict()
        return r

    def poner_luces(self, perfil: int, modo: int, color: str, solo_probar: bool = False) -> dict[str, Any]:
        """Luces de un perfil. Con ``solo_probar`` se mandan sin guardarlas."""
        luces = Luces(modo, color)  # ErrorProtocolo -> 400
        if not solo_probar:
            p = self.ajustes.perfil(perfil)
            p.luces_modo, p.luces_color = luces.modo, luces.color
            self.ajustes.guardar_perfil(perfil, p)
            self.ajustes.guardar()
        if not self.estado.presencia.configurable:
            self.publicar("estado")
            return self._sin_cable(luces=luces.como_dict())
        self._escribir([protocolo.mensaje_de_luces(perfil, luces)])
        self.publicar("estado")
        return {"escrito": True, "luces": luces.como_dict(), "perfil": perfil, "probado": solo_probar}

    def restablecer(self, perfil: int | None = None) -> dict[str, Any]:
        """Vuelve un perfil (o los tres) a como los deja la Botonera de inicio."""
        indices = [perfil] if perfil is not None else list(range(protocolo.NUMERO_DE_PERFILES))
        for i in indices:
            self.ajustes.guardar_perfil(i, Perfil.inicial(i))
        self.ajustes.guardar()
        if not self.estado.presencia.configurable:
            self.publicar("estado")
            return self._sin_cable()
        if perfil is None:
            return self.aplicar()
        return self.aplicar(perfil)

    def poner_escribir_al_conectar(self, valor: bool) -> dict[str, Any]:
        self.ajustes.escribir_al_conectar = bool(valor)
        self.ajustes.guardar()
        self.publicar("estado")
        return {"escribir_al_conectar": self.ajustes.escribir_al_conectar}

    # --- escuchar ------------------------------------------------------------------

    def escuchar(self, segundos: float = 10.0) -> dict[str, Any]:
        """Escucha las pulsaciones del teclado unos segundos y las devuelve."""
        segundos = max(1.0, min(float(segundos), 60.0))
        self.estado.escuchando = True
        self.publicar("estado")
        try:
            pulsaciones = escucha.capturar(segundos)
        finally:
            self.estado.escuchando = False
            self.publicar("estado")
        return {"segundos": segundos, "pulsaciones": pulsaciones}
