"""El servicio: vigila el teclado y le graba lo que dice la configuración.

Como el teclado no se puede leer, el servicio no «compara y corrige» como
hacen MiniMic y SikaiMini: **graba entero**. Al verlo por cable (si
``escribir_al_conectar`` está encendido) le manda los tres perfiles con sus
21 piezas y sus luces; cada cambio desde el panel graba la pieza o las luces
tocadas en el momento, y guarda la configuración, que es la única copia de
lo que el teclado tiene.

La tecla de dictado funciona como en los otros tres teclados: cualquier pieza
puesta a ``ctrl-mayus-alt-f12`` (combinación que solo reserva este servicio;
F12 y no F16 porque por Bluetooth las F13-F24 no llegan)
trae al frente el programa elegido —o el que esté activo: Claude, ChatGPT,
Cursor— y alterna su dictado con ``tecladoia.dictado``. El teclado no lleva
micrófono, así que habla el del sistema. Las combinaciones de los otros
servicios (F13, F14, F15) también se pueden poner en una tecla.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from minimic.tunel import Tunel, analizar_portero, se_puede_usar_el_origen
from tecladoia.sucesos import Bus

from . import __version__, dispositivo, escucha, lanzador, protocolo
from .config import ATAJO_MICROFONO, Ajustes, Perfil, aplicar_atajos_de_dictado
from .protocolo import ErrorProtocolo, Luces

registro = logging.getLogger("botonera.servicio")

VK_F12 = 0x7B
IDENTIFICADOR_ATAJO = 0xA17D
NOMBRE_ATAJO = "ctrl+alt+may+f12"


@dataclass
class Estado:
    presencia: dispositivo.Presencia = field(default_factory=dispositivo.Presencia)
    escribiendo: bool = False
    escuchando: bool = False
    ultima_escritura: str = ""
    mensajes_escritos: int = 0
    dictado_abierto: bool = False
    ultima_pulsacion: float = 0.0
    atajo_reservado: bool | None = None
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
        self._tunel: Tunel | None = None
        self._tarea_tunel: asyncio.Task | None = None
        self.motivo_sin_tunel = ""
        self._dictado: Any = None
        self._escucha: Any = None
        self._escucha_aplicaciones: lanzador.EscuchaAtajos | None = None

    # --- arranque y parada ------------------------------------------------

    async def arrancar(self) -> None:
        self.bucle = asyncio.get_running_loop()
        self._preparar_dictado()
        self._preparar_lanzadores()
        self._hilos.append(dispositivo.vigilar_presencia(self._al_cambiar_presencia, parar=self._parar))
        self.asegurar_tunel()
        registro.info("Botonera %s en marcha", __version__)

    async def detener(self) -> None:
        self._parar.set()
        if self._tunel is not None:
            self._tunel.parar()
        if self._escucha is not None:
            try:
                self._escucha.parar()
            except Exception:  # noqa: BLE001
                pass
        if self._escucha_aplicaciones is not None:
            self._escucha_aplicaciones.parar()

    # --- teclas que abren aplicaciones -------------------------------------------

    def _preparar_lanzadores(self) -> None:
        if not lanzador.hay_soporte():
            return
        self._escucha_aplicaciones, hilo = lanzador.hilo_de_escucha(self.al_pulsar_aplicacion)
        self._hilos.append(hilo)

    def al_pulsar_aplicacion(self, hueco: int) -> dict[str, Any]:
        """Llegó Ctrl+Mayús+Alt+F<hueco>: se abre la aplicación de ese hueco, si la hay."""
        datos = self.ajustes.lanzadores.get(str(hueco))
        if not datos:
            registro.info("tecla de aplicación %d sin aplicación asignada", hueco)
            return {"hueco": hueco, "abierta": False}
        try:
            lanzador.abrir(datos["destino"])
            registro.info("tecla de aplicación %d: abre %s", hueco, datos["nombre"])
            self.publicar("aplicacion", {"hueco": hueco, "nombre": datos["nombre"]})
            return {"hueco": hueco, "abierta": True, "nombre": datos["nombre"]}
        except Exception as e:  # noqa: BLE001
            self._avisar(f"no se pudo abrir {datos['nombre']}: {e}")
            return {"hueco": hueco, "abierta": False, "error": str(e)}

    def lanzadores(self) -> dict[str, dict[str, Any]]:
        return {h: {**d, "accion": lanzador.accion_del_hueco(int(h))} for h, d in sorted(self.ajustes.lanzadores.items(), key=lambda kv: int(kv[0]))}

    def asignar_aplicacion(self, perfil: int, pieza: int, nombre: str, destino: str) -> dict[str, Any]:
        """Deja la pieza abriendo esa aplicación: reutiliza su hueco o toma uno libre, y graba la pieza."""
        nombre, destino = (nombre or "").strip(), (destino or "").strip()
        if not destino:
            raise ValueError("falta «destino» (el AppID de la aplicación o su ruta)")
        hueco = next((int(h) for h, d in self.ajustes.lanzadores.items() if d.get("destino") == destino), None)
        if hueco is None:
            libres = [h for h in lanzador.HUECOS if str(h) not in self.ajustes.lanzadores]
            if not libres:
                raise ValueError("los once huecos de aplicaciones están ocupados; quita alguno en la pestaña Aplicaciones")
            hueco = libres[0]
            self.ajustes.lanzadores[str(hueco)] = {"nombre": nombre or destino, "destino": destino}
        r = self.poner_pieza(perfil, pieza, lanzador.accion_del_hueco(hueco))
        r["hueco"] = hueco
        r["aplicacion"] = self.ajustes.lanzadores[str(hueco)]
        return r

    def quitar_lanzador(self, hueco: int) -> dict[str, Any]:
        quitado = self.ajustes.lanzadores.pop(str(hueco), None)
        self.ajustes.guardar()
        self.publicar("estado")
        return {"hueco": hueco, "quitado": quitado}

    # --- la tecla de dictado ------------------------------------------------------

    def _preparar_dictado(self) -> None:
        try:
            from tecladoia.dictado import Dictado, EscuchaDictado, hay_soporte
        except Exception as e:  # noqa: BLE001
            self._avisar(f"sin dictado: {e}")
            return
        self._dictado = Dictado()
        self._dictado.usar_el_propio = self.ajustes.usar_microfono_propio
        aplicar_atajos_de_dictado(self.ajustes.atajos_dictado)
        if not hay_soporte():
            self.estado.atajo_reservado = False
            return
        self._escucha = EscuchaDictado(self.al_pulsar_microfono, IDENTIFICADOR_ATAJO, VK_F12, NOMBRE_ATAJO)
        hilo = threading.Thread(target=self._correr_escucha, name="botonera-atajo", daemon=True)
        hilo.start()
        self._hilos.append(hilo)

    def _correr_escucha(self) -> None:
        self.estado.atajo_reservado = True
        try:
            self._escucha.correr()
        finally:
            self.estado.atajo_reservado = False

    @staticmethod
    def _proceso_al_frente() -> str:
        try:
            from tecladoia.enfoque import _ventana_al_frente
            ventana = _ventana_al_frente()
            return ventana.proceso if ventana else ""
        except Exception:  # noqa: BLE001
            return ""

    def al_pulsar_microfono(self) -> dict[str, Any]:
        """Lo que pasa cuando llega la combinación de la tecla de dictado.

        Trae al frente el programa elegido —o el que esté activo, si así está
        configurado— y alterna su dictado: el botón propio de Claude o ChatGPT
        si lo tienen, Win+H si no.
        """
        if self._dictado is None:
            return {"accion": "sin dictado"}
        programa = self.ajustes.programa_elegido(self._proceso_al_frente())
        if self.ajustes.pitido_al_abrir and not self._dictado.abierto:
            try:
                from tecladoia.sonido import avisar
                avisar()
            except Exception:  # noqa: BLE001
                pass
        self._dictado.usar_el_propio = self.ajustes.usar_microfono_propio
        hecho = self._dictado.alternar(
            programa["proceso"], programa["lanzar"],
            pinchar_el_cuadro=self.ajustes.pinchar_cuadro,
            enviar_al_cerrar=self.ajustes.enviar_al_cerrar,
            alto_del_cuadro=self.ajustes.alto_cuadro,
        )
        self.estado.dictado_abierto = bool(self._dictado.abierto)
        self.estado.ultima_pulsacion = time.time()
        registro.info(
            "tecla de dictado: %s (%s, %s)", hecho.get("accion"), programa["nombre"],
            "micrófono propio" if hecho.get("con_el_propio") else "Win+H",
        )
        self.publicar("pulsacion", {"accion": hecho.get("accion"), "programa": programa["nombre"],
                                    "con_el_propio": bool(hecho.get("con_el_propio"))})
        self.publicar("estado")
        return hecho

    # --- el túnel al portero (ledblanco.proyectoia.org) ---------------------------

    def asegurar_tunel(self) -> None:
        """Abre (o cierra) el túnel según la configuración. Se puede llamar las veces que haga falta."""
        destino = analizar_portero(self.ajustes.portero, 8029) if self.ajustes.usar_portero else None
        if destino is None:
            self.motivo_sin_tunel = "apagado en la configuración" if not self.ajustes.usar_portero else "sin dirección del portero"
        elif not self.ajustes.clave_panel:
            self.motivo_sin_tunel = "el panel no tiene clave: sin clave no se publica"
            destino = None
        elif not se_puede_usar_el_origen():
            self.motivo_sin_tunel = "este sistema no deja salir desde 127.0.0.2, y sin eso el panel tomaría Internet por local"
            destino = None
        else:
            self.motivo_sin_tunel = ""
        quiere = destino is not None
        tiene = self._tunel is not None and self._tarea_tunel is not None and not self._tarea_tunel.done()
        if tiene and (not quiere or self._tunel.portero != destino):  # type: ignore[union-attr]
            self._tunel.parar()  # type: ignore[union-attr]
            self._tunel = None
            tiene = False
        if quiere and not tiene and self.bucle is not None:
            self._tunel = Tunel("botonera", self.ajustes.puerto_panel, destino, self._presentacion)  # type: ignore[arg-type]
            self._tarea_tunel = self.bucle.create_task(self._tunel.mantener())

    def _presentacion(self) -> dict[str, Any]:
        import socket
        try:
            equipo = socket.gethostname()
        except OSError:
            equipo = ""
        return {"equipo": equipo, "teclado": self.estado.presencia.conectado}

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
            "lanzadores": self.lanzadores(),
            "dictado": {"abierto": e.dictado_abierto, "programa": self.ajustes.programa_elegido()["nombre"],
                        "sigue_a_la_activa": self.ajustes.programa == "activo", "atajo": NOMBRE_ATAJO,
                        "accion": ATAJO_MICROFONO, "atajo_reservado": e.atajo_reservado},
            "tunel": {**(self._tunel.resumen() if self._tunel else {"conectado": False, "portero": self.ajustes.portero}),
                      "motivo": self.motivo_sin_tunel},
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

    #: Cuánto se espera entre las teclas y las luces: recién grabadas 42 teclas,
    #: el firmware sigue escribiendo en flash y la orden de luces se perdía.
    PAUSA_ANTES_DE_LUCES_S = 0.6

    def aplicar(self, perfil: int | None = None) -> dict[str, Any]:
        """Graba los tres perfiles (o uno) tal como están en la configuración: primero las teclas, luego las luces."""
        indices = [perfil] if perfil is not None else list(range(protocolo.NUMERO_DE_PERFILES))
        teclas: list[bytes] = []
        luces: list[bytes] = []
        for i in indices:
            p = self.ajustes.perfil(i)
            teclas.extend(protocolo.mensajes_de_perfil(i, p.acciones()))
            luces.append(protocolo.mensaje_de_luces(i, p.luces()))
        if not self.estado.presencia.configurable:
            return self._sin_cable(mensajes=len(teclas) + len(luces))
        n = self._escribir(teclas)
        time.sleep(self.PAUSA_ANTES_DE_LUCES_S)
        n += self._escribir(luces)
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
        # Grabar una tecla puede dejar las luces a oscuras: se le recuerdan.
        time.sleep(self.PAUSA_ANTES_DE_LUCES_S / 2)
        self._escribir([protocolo.mensaje_de_luces(perfil, p.luces())])
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
