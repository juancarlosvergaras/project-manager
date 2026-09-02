"""El servicio: vigila el teclado, cuida el micrófono y atiende la tecla blanca.

Qué hace, en orden de importancia:

1. **La tecla blanca abre el dictado donde toca.** El teclado la manda como
   ``Ctrl+Mayús+Alt+F14`` (se le escribe así al conectarlo por cable), el
   servicio la reserva como combinación global y al recibirla enfoca el
   programa elegido, pincha su cuadro de escribir y abre Win+H. La segunda
   pulsación cierra el dictado y, si se quiere, manda Intro. Todo eso lo hace
   ``tecladoia.dictado``, que no sabe de qué teclado viene la orden.
2. **El micrófono del teclado es el del sistema.** Cuando aparece —por cable o
   por el receptor de 2,4 GHz— se pone como micrófono predeterminado, que es
   el que usa el dictado de Windows. Así se habla desde lejos.
3. **El teclado queda como se quiere.** Al verlo por cable, se compara lo que
   trae con lo configurado y se escribe la diferencia: las cinco teclas y el
   modo del micrófono.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from tecladoia.sucesos import Bus

from . import __version__, dispositivo, protocolo
from .config import ATAJO_MICROFONO, TECLAS_DE_FABRICA, Ajustes
from .protocolo import Atajo

registro = logging.getLogger("minimic.servicio")

#: Combinación privada de MiniMic. F14: el AhaKey ya tiene F13 y Windows no
#: deja que dos procesos reserven la misma.
VK_F14 = 0x7D
IDENTIFICADOR_ATAJO = 0xA17B
NOMBRE_ATAJO = "ctrl+alt+may+f14"


@dataclass
class Estado:
    presencia: dispositivo.Presencia = field(default_factory=dispositivo.Presencia)
    mapa: list[str] = field(default_factory=list)  #: qué hace cada tecla, leído del teclado
    modo_microfono: int | None = None  #: lo que dice el teclado
    microfono: str = ""  #: nombre del micrófono del teclado, si está
    microfono_es_el_del_sistema: bool = False
    dictado_abierto: bool = False
    ultima_pulsacion: float = 0.0
    atajo_reservado: bool | None = None
    avisos: list[str] = field(default_factory=list)


class Servicio:
    def __init__(self, ajustes: Ajustes, teclado: dispositivo.Teclado | None = None) -> None:
        self.ajustes = ajustes
        self.teclado = teclado or dispositivo.Teclado()
        self.estado = Estado()
        self.bus = Bus()
        self.bucle: asyncio.AbstractEventLoop | None = None
        self._parar = threading.Event()
        self._dictado: Any = None
        self._escucha: Any = None
        self._hilos: list[threading.Thread] = []
        self._cerrojo = threading.Lock()

    # --- arranque y parada ------------------------------------------------

    async def arrancar(self) -> None:
        self.bucle = asyncio.get_running_loop()
        self._preparar_dictado()
        self._hilos.append(dispositivo.vigilar_presencia(self._al_cambiar_presencia, parar=self._parar))
        registro.info("MiniMic %s en marcha", __version__)

    async def detener(self) -> None:
        self._parar.set()
        if self._escucha is not None:
            try:
                self._escucha.parar()
            except Exception:  # noqa: BLE001
                pass

    # --- lo que ve el panel ---------------------------------------------------

    def resumen(self) -> dict[str, Any]:
        e = self.estado
        programa = self.ajustes.programa_elegido()
        return {
            "version": __version__,
            "conexion": {
                "cable": e.presencia.cable,
                "receptor": e.presencia.receptor,
                "conectado": e.presencia.conectado,
                "configurable": e.presencia.configurable,
                "descripcion": e.presencia.descripcion,
            },
            "mapa": e.mapa or self.ajustes.ultimo_mapa,
            "mapa_es_reciente": bool(e.mapa),
            "teclas_deseadas": list(self.ajustes.teclas),
            "modo_microfono": e.modo_microfono,
            "microfono": {"nombre": e.microfono, "es_el_del_sistema": e.microfono_es_el_del_sistema},
            "dictado": {"abierto": e.dictado_abierto, "programa": programa["nombre"], "atajo": NOMBRE_ATAJO,
                        "atajo_reservado": e.atajo_reservado},
            "avisos": list(e.avisos),
        }

    def publicar(self, tipo: str, datos: dict[str, Any] | None = None) -> None:
        """Manda un suceso al panel desde cualquier hilo."""
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

    # --- presencia y configuración del teclado ------------------------------

    def _al_cambiar_presencia(self, presencia: dispositivo.Presencia) -> None:
        self.estado.presencia = presencia
        registro.info("teclado: %s", presencia.descripcion)
        if presencia.configurable:
            time.sleep(1.0)  # Windows termina de montar las interfaces
            self.asegurar_teclado()
        else:
            self.estado.mapa = []
            self.estado.modo_microfono = None
        if presencia.conectado:
            self.cuidar_microfono()
        else:
            self.estado.microfono = ""
            self.estado.microfono_es_el_del_sistema = False
        self.publicar("estado")

    def asegurar_teclado(self) -> None:
        """Lee el teclado y le escribe lo que difiera de lo configurado."""
        try:
            deseadas = [Atajo.desde_texto(t) for t in self.ajustes.teclas]
        except protocolo.ErrorProtocolo as e:
            self._avisar(f"hay una tecla mal escrita en la configuración: {e}")
            deseadas = []
        try:
            mapa = self.teclado.leer_capa(0)
            ajustes = self.teclado.ajustes()
        except dispositivo.ErrorDispositivo as e:
            self._avisar(f"no se pudo leer el teclado: {e}")
            return
        cambios = 0
        for indice, atajo in enumerate(deseadas):
            if mapa.teclas.get(indice) != atajo:
                try:
                    self.teclado.escribir_tecla(0, indice, atajo)
                    mapa.teclas[indice] = atajo
                    cambios += 1
                except dispositivo.ErrorDispositivo as e:
                    self._avisar(f"la tecla {indice + 1} no se dejó escribir: {e}")
        if ajustes.modo_microfono != self.ajustes.modo_microfono:
            try:
                self.teclado.modo_microfono(self.ajustes.modo_microfono)
                ajustes = protocolo.Ajustes(self.ajustes.modo_microfono)
                cambios += 1
            except dispositivo.ErrorDispositivo as e:
                self._avisar(f"el modo del micrófono no se dejó escribir: {e}")
        self.estado.mapa = [str(mapa.teclas[i]) for i in range(protocolo.NUMERO_DE_TECLAS)]
        self.estado.modo_microfono = ajustes.modo_microfono
        self.ajustes.ultimo_mapa = list(self.estado.mapa)
        try:
            self.ajustes.guardar()
        except OSError as e:
            registro.warning("no se pudo guardar el último mapa: %s", e)
        if cambios:
            registro.info("teclado puesto al día: %d cambio(s)", cambios)

    def leer_teclado(self) -> dict[str, Any]:
        mapa = self.teclado.leer_capa(0)
        ajustes = self.teclado.ajustes()
        self.estado.mapa = [str(mapa.teclas[i]) for i in range(protocolo.NUMERO_DE_TECLAS)]
        self.estado.modo_microfono = ajustes.modo_microfono
        self.ajustes.ultimo_mapa = list(self.estado.mapa)
        self.ajustes.guardar()
        self.publicar("estado")
        return {"mapa": self.estado.mapa, "modo_microfono": self.estado.modo_microfono}

    def poner_teclas(self, textos: list[str]) -> dict[str, Any]:
        """Guarda las teclas deseadas y, si el teclado está por cable, las escribe."""
        if len(textos) != protocolo.NUMERO_DE_TECLAS:
            raise ValueError(f"hacen falta {protocolo.NUMERO_DE_TECLAS} teclas")
        atajos = [Atajo.desde_texto(t) for t in textos]  # ErrorProtocolo -> 400
        self.ajustes.teclas = [str(a) for a in atajos]
        self.ajustes.guardar()
        if self.estado.presencia.configurable:
            self.asegurar_teclado()
            self.publicar("estado")
            return {"escrito": True, "mapa": self.estado.mapa}
        return {"escrito": False, "mapa": self.estado.mapa,
                "aviso": "guardado; se escribirá al teclado cuando esté por cable"}

    def volver_a_fabrica(self) -> dict[str, Any]:
        return self.poner_teclas(list(TECLAS_DE_FABRICA))

    def poner_modo_microfono(self, modo: int) -> dict[str, Any]:
        if modo not in (protocolo.MICROFONO_MANTENER, protocolo.MICROFONO_PULSAR):
            raise ValueError("modo desconocido")
        self.ajustes.modo_microfono = modo
        self.ajustes.guardar()
        if self.estado.presencia.configurable:
            self.teclado.modo_microfono(modo)
            self.estado.modo_microfono = modo
            self.publicar("estado")
            return {"escrito": True, "modo": modo}
        return {"escrito": False, "modo": modo, "aviso": "guardado; se escribirá cuando esté por cable"}

    # --- micrófono ----------------------------------------------------------------

    def cuidar_microfono(self, forzar: bool = False) -> dict[str, Any]:
        try:
            micros = [m for m in dispositivo.microfonos_del_teclado() if m.activo]
        except dispositivo.ErrorDispositivo as e:
            self._avisar(str(e))
            return {"microfono": "", "es_el_del_sistema": False}
        if not micros:
            self.estado.microfono = ""
            self.estado.microfono_es_el_del_sistema = False
            return {"microfono": "", "es_el_del_sistema": False}
        elegido = micros[0]
        actual = dispositivo.microfono_predeterminado()
        es = any(m.identificador == actual for m in micros)
        if not es and (forzar or self.ajustes.adoptar_microfono):
            try:
                dispositivo.hacer_predeterminado(elegido.identificador)
                es = True
                registro.info("micrófono del sistema: el del teclado")
            except Exception as e:  # noqa: BLE001
                self._avisar(f"no se pudo poner el micrófono del teclado como predeterminado: {e}")
        self.estado.microfono = elegido.nombre
        self.estado.microfono_es_el_del_sistema = es
        return {"microfono": elegido.nombre, "es_el_del_sistema": es}

    # --- la tecla blanca ----------------------------------------------------------

    def _preparar_dictado(self) -> None:
        try:
            from tecladoia.dictado import Dictado, EscuchaDictado, hay_soporte
        except Exception as e:  # noqa: BLE001
            self._avisar(f"sin dictado: {e}")
            return
        self._dictado = Dictado()
        if not hay_soporte():
            self.estado.atajo_reservado = False
            return
        self._escucha = EscuchaDictado(self.al_pulsar_microfono, IDENTIFICADOR_ATAJO, VK_F14, NOMBRE_ATAJO)
        hilo = threading.Thread(target=self._correr_escucha, name="minimic-atajo", daemon=True)
        hilo.start()
        self._hilos.append(hilo)

    def _correr_escucha(self) -> None:
        self.estado.atajo_reservado = True
        try:
            self._escucha.correr()
        finally:
            self.estado.atajo_reservado = False

    def al_pulsar_microfono(self) -> dict[str, Any]:
        """Lo que pasa cuando llega la combinación de la tecla blanca."""
        if self._dictado is None:
            return {"accion": "sin dictado"}
        programa = self.ajustes.programa_elegido()
        if self.ajustes.pitido_al_abrir and not self._dictado.abierto:
            try:
                from tecladoia.sonido import avisar
                avisar()
            except Exception:  # noqa: BLE001
                pass
        hecho = self._dictado.alternar(
            programa["proceso"], programa["lanzar"],
            pinchar_el_cuadro=self.ajustes.pinchar_cuadro,
            enviar_al_cerrar=self.ajustes.enviar_al_cerrar,
            alto_del_cuadro=self.ajustes.alto_cuadro,
        )
        self.estado.dictado_abierto = bool(self._dictado.abierto)
        self.estado.ultima_pulsacion = time.time()
        registro.info("tecla del micrófono: %s (%s)", hecho.get("accion"), programa["nombre"])
        self.publicar("pulsacion", {"tecla": 5, "accion": hecho.get("accion"), "programa": programa["nombre"]})
        self.publicar("estado")
        return hecho
