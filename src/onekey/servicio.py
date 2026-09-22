"""El servicio de OneKey: oye el botón, cuida su micrófono y abre el dictado.

Tres piezas, todas prestadas:

1. **El botón se reconoce, no se remapea** (``minimic.boton``): manda Alt
   derecho y por Bluetooth no se le puede cambiar. Raw Input dice de qué
   aparato viene cada pulsación; solo la del AI_VOICE cuenta.
2. **Su micrófono manos libres es el del sistema** cuando aparece y cada vez
   que se pulsa (``minimic.dispositivo``, por el identificador de contenedor).
3. **El dictado es el de siempre** (``tecladoia.dictado``): botón propio de
   Claude o ChatGPT, Win+H de respaldo, y el Intro que para y envía.

No hay combinación privada que reservar; se reserva una que nadie usa
(``Ctrl+Mayús+Alt+F17``) solo para tener el gancho del Intro, y de paso sirve
para probar el dictado sin el botón.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from minimic import boton, dispositivo
from tecladoia.sucesos import Bus
from tecladoia.tunel import Tunel, analizar_portero, se_puede_usar_el_origen

from . import __version__
from .config import Ajustes, aplicar_atajos_de_dictado

registro = logging.getLogger("onekey.servicio")

VK_F17 = 0x80
IDENTIFICADOR_ATAJO = 0xA17E
NOMBRE_ATAJO = "ctrl+alt+may+f17"


def _nombre_del_equipo() -> str:
    import socket
    try:
        return socket.gethostname()
    except OSError:
        return ""


@dataclass
class Estado:
    boton: boton.Boton | None = None
    oyendo: bool = False
    microfono: str = ""
    microfono_es_el_del_sistema: bool = False
    dictado_abierto: bool = False
    ultima_pulsacion: float = 0.0
    pulsaciones: int = 0
    atajo_reservado: bool | None = None
    avisos: list[str] = field(default_factory=list)


class Servicio:
    def __init__(self, ajustes: Ajustes) -> None:
        self.ajustes = ajustes
        self.estado = Estado()
        self.bus = Bus()
        self.bucle: asyncio.AbstractEventLoop | None = None
        self._parar = threading.Event()
        self._dictado: Any = None
        self._escucha: Any = None
        self._escucha_boton: boton.EscuchaBoton | None = None
        self._hilos: list[threading.Thread] = []
        self._cerrojo = threading.Lock()
        self._tunel: Tunel | None = None
        self._tarea_tunel: asyncio.Task | None = None
        self.motivo_sin_tunel = ""

    # --- arranque y parada ------------------------------------------------

    async def arrancar(self) -> None:
        self.bucle = asyncio.get_running_loop()
        self._preparar_dictado()
        self._preparar_boton()
        self.asegurar_tunel()
        registro.info("OneKey %s en marcha", __version__)

    async def detener(self) -> None:
        self._parar.set()
        if self._tunel is not None:
            self._tunel.parar()
        for escucha in (self._escucha, self._escucha_boton):
            if escucha is not None:
                try:
                    escucha.parar()
                except Exception:  # noqa: BLE001
                    pass

    # --- el túnel al portero ----------------------------------------------------

    def asegurar_tunel(self) -> None:
        """Abre (o cierra) el túnel según la configuración. Se puede llamar las veces que haga falta."""
        destino = analizar_portero(self.ajustes.portero, 8033) if self.ajustes.usar_portero else None
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
            self._tunel = Tunel("onekey", self.ajustes.puerto_panel, destino, self._presentacion)  # type: ignore[arg-type]
            self._tarea_tunel = self.bucle.create_task(self._tunel.mantener())

    def _presentacion(self) -> dict[str, Any]:
        return {"equipo": _nombre_del_equipo(), "teclado": self.estado.boton is not None}

    # --- lo que ve el panel ---------------------------------------------------

    def resumen(self) -> dict[str, Any]:
        e = self.estado
        programa = self.ajustes.programa_elegido()
        return {
            "version": __version__,
            "boton": {
                "nombre": self.ajustes.boton_bluetooth,
                "buscado": bool(self.ajustes.boton_bluetooth.strip()),
                "conectado": e.boton is not None,
                "direccion": e.boton.direccion if e.boton else "",
                "oyendo": e.oyendo,
                "pulsaciones": e.pulsaciones,
                "ultima_pulsacion": e.ultima_pulsacion,
            },
            "microfono": {"nombre": e.microfono, "es_el_del_sistema": e.microfono_es_el_del_sistema},
            "dictado": {"abierto": e.dictado_abierto, "programa": programa["nombre"], "atajo": NOMBRE_ATAJO,
                        "atajo_reservado": e.atajo_reservado},
            "avisos": list(e.avisos),
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

    # --- el botón -------------------------------------------------------------------

    def _preparar_boton(self) -> None:
        if not boton.hay_soporte():
            self._avisar("el botón solo se puede oír en Windows")
            return
        self._escucha_boton = boton.EscuchaBoton(self._al_pulsar_boton)
        hilo = threading.Thread(target=self._correr_escucha_boton, name="onekey-boton-raw", daemon=True)
        hilo.start()
        self._hilos.append(hilo)
        self._hilos.append(boton.vigilar(self._nombre_del_boton, self._al_cambiar_boton, parar=self._parar))

    def _correr_escucha_boton(self) -> None:
        assert self._escucha_boton is not None
        try:
            self._escucha_boton.correr()
        finally:
            self.estado.oyendo = False

    def _nombre_del_boton(self) -> str:
        return (self.ajustes.boton_bluetooth or "").strip()

    def _al_cambiar_boton(self, encontrado: boton.Boton | None) -> None:
        self.estado.boton = encontrado
        self.estado.oyendo = bool(self._escucha_boton and self._escucha_boton.escuchando)
        if self._escucha_boton is not None:
            self._escucha_boton.apuntar_a(encontrado.rutas_hid if encontrado else [])
        if encontrado is not None:
            registro.info("botón: %s", encontrado.descripcion)
            time.sleep(1.0)  # Windows termina de montar el manos libres
            self.cuidar_microfono()
        else:
            registro.info("botón: no está")
            self.estado.microfono = ""
            self.estado.microfono_es_el_del_sistema = False
        self.publicar("estado")

    def buscar_boton(self) -> dict[str, Any]:
        """Vuelve a mirar ahora mismo (botón del panel)."""
        encontrado = boton.buscar(self._nombre_del_boton())
        firma_vieja = self.estado.boton.direccion if self.estado.boton else ""
        if (encontrado.direccion if encontrado else "") != firma_vieja:
            self._al_cambiar_boton(encontrado)
        return self.resumen()["boton"]

    def _al_pulsar_boton(self) -> None:
        """Llega desde el hilo de Raw Input (ya en un hilo aparte)."""
        self.estado.pulsaciones += 1
        # Al pulsar el botón se habla por su micrófono: se pone como el del
        # sistema en ese momento, por si otro aparato lo había desplazado.
        self.cuidar_microfono()
        self.al_pulsar_microfono(origen="botón")

    # --- micrófono ----------------------------------------------------------------

    def cuidar_microfono(self, forzar: bool = False) -> dict[str, Any]:
        b = self.estado.boton
        if b is None or not b.contenedor:
            self.estado.microfono = ""
            self.estado.microfono_es_el_del_sistema = False
            return {"microfono": "", "es_el_del_sistema": False}
        try:
            micros = [m for m in dispositivo.microfonos_del_teclado({b.contenedor}) if m.activo]
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
                registro.info("micrófono del sistema: el del botón (%s)", elegido.nombre)
            except Exception as e:  # noqa: BLE001
                self._avisar(f"no se pudo poner el micrófono del botón como predeterminado: {e}")
        self.estado.microfono = elegido.nombre
        self.estado.microfono_es_el_del_sistema = es
        return {"microfono": elegido.nombre, "es_el_del_sistema": es}

    # --- el dictado ------------------------------------------------------------------

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
        # La combinación reservada solo sirve para probar y para tener el
        # gancho del Intro; el botón no pasa por aquí.
        self._escucha = EscuchaDictado(
            self.al_pulsar_microfono, IDENTIFICADOR_ATAJO, VK_F17, NOMBRE_ATAJO,
            al_intro=self.al_pulsar_intro, capturar_intro=self._dictado.intro_es_nuestro,
        )
        hilo = threading.Thread(target=self._correr_escucha, name="onekey-atajo", daemon=True)
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

    def al_pulsar_intro(self) -> None:
        """Intro con el micrófono propio grabando: parar y enviar."""
        if self._dictado is None:
            return
        programa = self.ajustes.programa_elegido(self._proceso_al_frente())
        hecho = self._dictado.aceptar(programa["proceso"])
        self.estado.dictado_abierto = bool(self._dictado.abierto)
        registro.info("intro con el micrófono grabando: %s (%s)", hecho.get("accion"), programa["nombre"])
        self.publicar("pulsacion", {"tecla": "intro", "accion": hecho.get("accion"), "programa": programa["nombre"]})
        self.publicar("estado")

    def al_pulsar_microfono(self, origen: str = "prueba") -> dict[str, Any]:
        """Lo que pasa cuando se pulsa el botón (o la combinación de prueba)."""
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
            "%s: %s (%s, %s)", origen, hecho.get("accion"), programa["nombre"],
            "micrófono propio" if hecho.get("con_el_propio") else "Win+H",
        )
        self.publicar("pulsacion", {"tecla": "boton" if origen == "botón" else "prueba", "accion": hecho.get("accion"),
                                    "programa": programa["nombre"], "con_el_propio": bool(hecho.get("con_el_propio"))})
        self.publicar("estado")
        return hecho
