"""El servicio: vigila el teclado, cuida el micrófono y atiende la tecla del micrófono.

Calcado del de MiniMic, con tres diferencias:

1. **Seis piezas, no cinco.** Tres teclas y los tres gestos de la perilla, y
   dos familias de registro más (ratón y multimedia). La perilla se deja como
   rueda del ratón, que es para lo que se compró.
2. **La combinación privada es ``Ctrl+Mayús+Alt+F15``.** F13 es del AhaKey y
   F14 del MiniMic; Windows solo deja reservar cada combinación a un proceso.
3. **Las luces.** Se leen al conectar por cable y, si en la configuración hay
   un modo elegido, se le escriben si difieren.

Todo lo del dictado lo hace ``tecladoia.dictado``, que no sabe de qué teclado
viene la orden, y a quién se le habla lo decide la misma ficha de programas
que MiniMic.
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
from .config import LUCES_SIN_TOCAR, TECLAS_DE_FABRICA, TECLAS_DESEADAS, Ajustes, aplicar_atajos_de_dictado
from .protocolo import Atajo, Luces

registro = logging.getLogger("sikaimini.servicio")

VK_F15 = 0x7E
IDENTIFICADOR_ATAJO = 0xA17C
NOMBRE_ATAJO = "ctrl+alt+may+f15"


@dataclass
class Estado:
    presencia: dispositivo.Presencia = field(default_factory=dispositivo.Presencia)
    mapa: list[str] = field(default_factory=list)
    modo_microfono: int | None = None
    luces: dict[str, Any] | None = None  #: lo último leído del teclado
    microfono: str = ""
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
        registro.info("SikaiMini %s en marcha", __version__)

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
            "piezas": list(protocolo.NOMBRES_DE_LAS_PIEZAS),
            "modo_microfono": e.modo_microfono,
            "luces": e.luces,
            "luces_deseadas": {"modo": self.ajustes.luces_modo, "color": self.ajustes.luces_color},
            "microfono": {"nombre": e.microfono, "es_el_del_sistema": e.microfono_es_el_del_sistema},
            "dictado": {"abierto": e.dictado_abierto, "programa": programa["nombre"], "atajo": NOMBRE_ATAJO,
                        "atajo_reservado": e.atajo_reservado},
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
            self.estado.luces = None
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
            self._avisar(f"hay una pieza mal escrita en la configuración: {e}")
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
                    self._avisar(f"la {protocolo.NOMBRES_DE_LAS_PIEZAS[indice]} no se dejó escribir: {e}")
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
        cambios += self._asegurar_luces()
        try:
            self.ajustes.guardar()
        except OSError as e:
            registro.warning("no se pudo guardar el último mapa: %s", e)
        if cambios:
            registro.info("teclado puesto al día: %d cambio(s)", cambios)

    def _asegurar_luces(self) -> int:
        try:
            luces = self.teclado.luces()
        except (dispositivo.ErrorDispositivo, protocolo.ErrorProtocolo) as e:
            self._avisar(f"no se pudieron leer las luces: {e}")
            return 0
        cambios = 0
        if self.ajustes.luces_modo != LUCES_SIN_TOCAR:
            deseadas = luces.con(self.ajustes.luces_modo, protocolo.color_desde_texto(self.ajustes.luces_color))
            if deseadas != luces:
                try:
                    self.teclado.poner_luces(deseadas)
                    luces = deseadas
                    cambios += 1
                except dispositivo.ErrorDispositivo as e:
                    self._avisar(f"las luces no se dejaron escribir: {e}")
        self.estado.luces = luces.como_dict()
        return cambios

    def leer_teclado(self) -> dict[str, Any]:
        mapa = self.teclado.leer_capa(0)
        ajustes = self.teclado.ajustes()
        self.estado.mapa = [str(mapa.teclas[i]) for i in range(protocolo.NUMERO_DE_TECLAS)]
        self.estado.modo_microfono = ajustes.modo_microfono
        self.ajustes.ultimo_mapa = list(self.estado.mapa)
        try:
            self.estado.luces = self.teclado.luces().como_dict()
        except (dispositivo.ErrorDispositivo, protocolo.ErrorProtocolo):
            pass
        self.ajustes.guardar()
        self.publicar("estado")
        return {"mapa": self.estado.mapa, "modo_microfono": self.estado.modo_microfono, "luces": self.estado.luces}

    def poner_teclas(self, textos: list[str]) -> dict[str, Any]:
        """Guarda lo deseado y, si el teclado está por cable, lo escribe."""
        if len(textos) != protocolo.NUMERO_DE_TECLAS:
            raise ValueError(f"hacen falta {protocolo.NUMERO_DE_TECLAS} piezas")
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

    def volver_a_lo_recomendado(self) -> dict[str, Any]:
        return self.poner_teclas(list(TECLAS_DESEADAS))

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

    # --- luces ---------------------------------------------------------------------

    def poner_luces(self, modo: int, color: str) -> dict[str, Any]:
        """Guarda modo y color, y si el teclado está por cable, se los graba."""
        if not isinstance(modo, int) or not LUCES_SIN_TOCAR <= modo <= 255:
            raise ValueError("el modo de las luces va de 0 a 255, o -1 para no tocarlas")
        rgb = protocolo.color_desde_texto(color)  # ErrorProtocolo -> 400
        self.ajustes.luces_modo = modo
        self.ajustes.luces_color = protocolo.color_a_texto(rgb)
        self.ajustes.guardar()
        if not self.estado.presencia.configurable:
            return {"escrito": False, "aviso": "guardado; se escribirá cuando esté por cable"}
        if modo == LUCES_SIN_TOCAR:
            self.publicar("estado")
            return {"escrito": False, "aviso": "las luces se dejan como estén en el teclado"}
        actuales = self.teclado.luces()
        nuevas = actuales.con(modo, rgb)
        self.teclado.poner_luces(nuevas)
        self.estado.luces = nuevas.como_dict()
        self.publicar("estado")
        return {"escrito": True, "luces": self.estado.luces}

    def leer_luces(self) -> dict[str, Any]:
        self.estado.luces = self.teclado.luces().como_dict()
        self.publicar("estado")
        return {"luces": self.estado.luces}

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

    # --- la tecla del micrófono ------------------------------------------------------

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
        self._escucha = EscuchaDictado(self.al_pulsar_microfono, IDENTIFICADOR_ATAJO, VK_F15, NOMBRE_ATAJO)
        hilo = threading.Thread(target=self._correr_escucha, name="sikaimini-atajo", daemon=True)
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
        """Lo que pasa cuando llega la combinación de la tecla del micrófono."""
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
            "tecla del micrófono: %s (%s, %s)", hecho.get("accion"), programa["nombre"],
            "micrófono propio" if hecho.get("con_el_propio") else "Win+H",
        )
        self.publicar("pulsacion", {"tecla": protocolo.TECLA_MICROFONO + 1, "accion": hecho.get("accion"),
                                    "programa": programa["nombre"], "con_el_propio": bool(hecho.get("con_el_propio"))})
        self.publicar("estado")
        return hecho
