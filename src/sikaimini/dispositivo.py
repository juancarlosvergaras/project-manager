"""El SiKai mini visto desde Windows: se apoya en el MiniMic y añade lo suyo.

Los dos teclados llevan el mismo chip Jieli y se presentan con el mismo
VID/PID —``514C:8850`` por cable, ``4C4A:4155`` por el receptor—, así que la
presencia, el canal HID y el manejo del micrófono son literalmente los de
``minimic.dispositivo``. Lo único que los distingue es lo que traen dentro:
**el MiniMic tiene cinco registros y este seis**. Por eso ``leer_capa`` exige
seis y se niega con cinco: si el que está por cable es el MiniMic, esta
aplicación no le escribe nada (y MiniMic hace lo mismo al revés).

Cuando los dos van por sus receptores a la vez no hay forma de saber cuál es
cuál sin leerlos, y por el receptor no se leen. Lo que hacen las dos
aplicaciones con un receptor —adoptar el micrófono, esperar la tecla— es
inofensivo hecho por partida doble, así que se deja estar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from minimic import dispositivo as _base
from minimic.dispositivo import (  # noqa: F401 - se reexportan tal cual
    _hid, PAGINA_DE_FABRICANTE, PID_CABLE, PID_RECEPTOR, VID_CABLE, VID_RECEPTOR, CanalHID, ErrorDispositivo,
    Microfono, Presencia, contenedores_del_teclado, hacer_predeterminado, microfono_predeterminado,
    microfonos_del_teclado, presencia, vigilar_presencia,
)

from . import protocolo
from .protocolo import Atajo, Luces

registro = logging.getLogger("sikaimini.dispositivo")


@dataclass
class Mapa:
    """La capa entera: qué hace cada pieza, contadas desde 0."""

    capa: int
    teclas: dict[int, Atajo] = field(default_factory=dict)

    def como_texto(self) -> dict[int, str]:
        return {t: str(a) for t, a in sorted(self.teclas.items())}


class Teclado(_base.Teclado):
    """Habla con el teclado por el cable, con las órdenes del SiKai mini."""

    def leer_capa(self, capa: int = 0) -> Mapa:
        mapa = Mapa(capa)
        for r in self._exigir_acuse(protocolo.leer_capa(capa), "leer la capa"):
            if r.orden == protocolo.ORDEN_REGISTRO_DE_TECLA:
                try:
                    mapa.teclas[r.arg] = Atajo.desde_registro(r.carga)
                except protocolo.ErrorProtocolo as e:
                    registro.warning("pieza %d ilegible: %s", r.arg + 1, e)
        if len(mapa.teclas) != protocolo.NUMERO_DE_TECLAS:
            raise ErrorDispositivo(
                f"este teclado tiene {len(mapa.teclas)} registros y el SiKai mini tiene {protocolo.NUMERO_DE_TECLAS}: "
                "no es él" + (" (¿es el MiniMic?)" if len(mapa.teclas) == 5 else "")
            )
        return mapa

    def escribir_tecla(self, capa: int, tecla: int, atajo: Atajo) -> None:  # type: ignore[override]
        nombre = protocolo.NOMBRES_DE_LAS_PIEZAS[tecla] if 0 <= tecla < protocolo.NUMERO_DE_TECLAS else f"pieza {tecla + 1}"
        self._exigir_acuse(protocolo.escribir_tecla(capa, tecla, atajo.a_registro()), f"cambio de la {nombre}")

    def luces(self) -> Luces:
        r = self._conversar(protocolo.leer_luces())
        if not r or r[0].orden != protocolo.ORDEN_LEER_LUCES:
            raise ErrorDispositivo("el teclado no dio sus luces")
        return Luces.desde_carga(r[0].carga)

    def poner_luces(self, luces: Luces) -> None:
        self._exigir_acuse(protocolo.escribir_luces(luces), "cambio de las luces")


    # --- para explorar el protocolo desde lejos ------------------------------

    def sondear(self, orden: int, capa: int = 0, arg: int = 0, carga: bytes = b"") -> list[dict]:
        """Manda una orden cruda (con su suma de control) y devuelve lo que conteste.

        Es la herramienta para buscar órdenes que no se conocen —la batería,
        por ejemplo— cuando el teclado está en otro PC y solo se llega por el
        túnel. Devuelve cada informe con su orden, capa, arg y carga en hex.
        """
        respuestas = self._conversar(protocolo.paquete(orden & 0xFF, capa & 0xFF, arg & 0xFF, carga))
        return [{"orden": f"{r.orden:#04x}", "capa": r.capa, "arg": r.arg, "carga": r.carga.hex(" "),
                 "acuse": r.es_acuse, "rechazo": r.es_rechazo} for r in respuestas]


def descriptores_del_teclado() -> list[dict]:
    """Las interfaces HID del teclado (cable y receptor) con su descriptor de informe.

    Si el receptor publica la batería como un uso HID (página 0x06, uso 0x20
    «Battery Strength», o la página 0x85), se ve aquí sin adivinar nada.
    """
    resultado: list[dict] = []
    try:
        aparatos = _hid().enumerate()
    except Exception as e:  # noqa: BLE001
        return [{"error": str(e)}]
    for a in aparatos:
        if (a["vendor_id"], a["product_id"]) not in ((VID_CABLE, PID_CABLE), (VID_RECEPTOR, PID_RECEPTOR)):
            continue
        ficha = {
            "vid": f"{a['vendor_id']:04x}", "pid": f"{a['product_id']:04x}", "serie": a.get("serial_number"),
            "interfaz": a.get("interface_number"), "pagina": f"{a.get('usage_page', 0):#06x}", "uso": f"{a.get('usage', 0):#04x}",
            "descriptor": "",
        }
        try:
            d = _hid().device()
            d.open_path(a["path"])
            try:
                ficha["descriptor"] = bytes(d.get_report_descriptor()).hex(" ")
            finally:
                d.close()
        except Exception as e:  # noqa: BLE001 - abrirla puede fallar; se anota
            ficha["descriptor"] = f"(no se pudo leer: {e})"
        resultado.append(ficha)
    return resultado
