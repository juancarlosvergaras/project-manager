"""La Botonera vista desde Windows: encontrarla, distinguirla y escribirle.

Se presenta con el mismo VID/PID que el MiniMic y el SiKai mini
(``514C:8850``), así que **hay que distinguirla antes de escribirle**: aquellos
dos hablan el protocolo LQ con suma de control y, si se les mandan estas
órdenes, las rechazan sin más daño; pero al revés, el MiniMic que viera esta
Botonera intentaría leerla y ella no contesta. La diferencia está en el
descriptor HID de la interfaz de fabricante: la Botonera declara informes de
**64 bytes** (``95 40``) y los otros dos de 63 (``95 3F``). Se mira eso, sin
mandar nada.

Por Bluetooth se llama «MINI_KEYBOARD» y Windows la enseña con VID/PID de
Apple (``05AC:022C``), como hacen estos chips. Por ahí funciona como teclado
pero no se configura: la interfaz de fabricante solo va por el cable.

Solo se escribe. El teclado no contesta nunca, así que el «canal» es abrir,
mandar los informes de 65 bytes con una pausa corta entre ellos, y cerrar.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from minimic.dispositivo import ErrorDispositivo, _hid  # noqa: F401 - se reexporta el error

from . import protocolo

registro = logging.getLogger("botonera.dispositivo")

VID, PID = 0x514C, 0x8850
PAGINA_DE_FABRICANTE = 0xFF00
VID_BLUETOOTH, PID_BLUETOOTH = 0x05AC, 0x022C
NOMBRE_BLUETOOTH = "MINI_KEYBOARD"

#: En el descriptor de informe: «Report Size 8, Report Count 64» es la Botonera;
#: «Report Count 63» son el MiniMic y el SiKai.
_INFORME_DE_64 = bytes.fromhex("75 08 95 40")
_INFORME_DE_63 = bytes.fromhex("75 08 95 3f")

PAUSA_ENTRE_MENSAJES_S = 0.03


@dataclass
class Presencia:
    cable: bool = False
    bluetooth: bool = False
    ruta: bytes | None = None
    serie: str = ""
    #: Hay un 514C:8850 por cable que NO es la Botonera (MiniMic o SiKai).
    otro_jieli: bool = False

    @property
    def conectado(self) -> bool:
        return self.cable or self.bluetooth

    @property
    def configurable(self) -> bool:
        return self.cable

    @property
    def descripcion(self) -> str:
        if self.cable and self.bluetooth:
            return "por cable y por Bluetooth"
        if self.cable:
            return "por cable"
        if self.bluetooth:
            return "por Bluetooth (funciona; para grabarla, cable)"
        if self.otro_jieli:
            return "no está (el teclado Jieli que hay por cable es otro)"
        return "no está"


def es_botonera(ruta: bytes) -> bool | None:
    """Mira el descriptor de la interfaz de fabricante. ``None`` si no se pudo leer."""
    try:
        d = _hid().device()
        d.open_path(ruta)
        try:
            descriptor = bytes(d.get_report_descriptor())
        finally:
            d.close()
    except Exception as e:  # noqa: BLE001
        registro.debug("descriptor ilegible: %s", e)
        return None
    if _INFORME_DE_64 in descriptor:
        return True
    if _INFORME_DE_63 in descriptor:
        return False
    return None


def presencia() -> Presencia:
    """Qué hay ahora mismo, según la lista HID de Windows."""
    try:
        aparatos = _hid().enumerate()
    except ErrorDispositivo:
        raise
    except Exception as e:  # noqa: BLE001
        raise ErrorDispositivo(f"no se pudo listar el HID: {e}") from e
    p = Presencia()
    for a in aparatos:
        vid, pid = a.get("vendor_id"), a.get("product_id")
        if (vid, pid) == (VID, PID) and a.get("usage_page") == PAGINA_DE_FABRICANTE:
            es = es_botonera(a["path"])
            if es:
                p.cable, p.ruta, p.serie = True, a["path"], str(a.get("serial_number") or "")
            elif es is False:
                p.otro_jieli = True
        elif (vid, pid) == (VID_BLUETOOTH, PID_BLUETOOTH):
            nombre = str(a.get("product_string") or "").upper()
            if NOMBRE_BLUETOOTH in nombre or "MINI" in nombre:
                p.bluetooth = True
    return p


class CanalHID:
    """La interfaz de fabricante abierta; solo escribe."""

    def __init__(self, ruta: bytes) -> None:
        self._d = _hid().device()
        self._d.open_path(ruta)

    def escribir(self, datos: bytes) -> None:
        if len(datos) != protocolo.TAMANO:
            raise ErrorDispositivo(f"informe de {len(datos)} bytes; el teclado quiere {protocolo.TAMANO}")
        n = self._d.write(datos)
        if n < 0:
            raise ErrorDispositivo("el teclado no aceptó el informe")

    def cerrar(self) -> None:
        try:
            self._d.close()
        except Exception:  # noqa: BLE001
            pass


class Teclado:
    """Manda mensajes a la Botonera por el cable. Sin respuestas que esperar."""

    def __init__(self, abrir_canal: Callable[[], Any] | None = None) -> None:
        self._abrir_canal = abrir_canal or self._abrir_por_cable
        self._cerrojo = threading.Lock()

    @staticmethod
    def _abrir_por_cable() -> CanalHID:
        p = presencia()
        if not p.cable or p.ruta is None:
            raise ErrorDispositivo("la Botonera no está por cable" + (" (el Jieli que hay es otro teclado)" if p.otro_jieli else ""))
        return CanalHID(p.ruta)

    def escribir(self, mensajes: list[bytes], pausa_s: float = PAUSA_ENTRE_MENSAJES_S) -> int:
        """Manda los mensajes en orden. Devuelve cuántos fueron."""
        with self._cerrojo:
            canal = self._abrir_canal()
            try:
                for m in mensajes:
                    canal.escribir(m)
                    if pausa_s:
                        time.sleep(pausa_s)
            finally:
                canal.cerrar()
        return len(mensajes)


def vigilar_presencia(al_cambiar: Callable[[Presencia], None], cada_s: float = 2.0, parar: threading.Event | None = None) -> threading.Thread:
    """Hilo que avisa cuando el teclado aparece o desaparece."""
    parar = parar or threading.Event()

    def bucle() -> None:
        ultima: Presencia | None = None
        while not parar.is_set():
            try:
                ahora = presencia()
            except ErrorDispositivo as e:
                registro.debug("presencia: %s", e)
                ahora = Presencia()
            if ultima is None or (ahora.cable, ahora.bluetooth, ahora.otro_jieli) != (ultima.cable, ultima.bluetooth, ultima.otro_jieli):
                ultima = ahora
                try:
                    al_cambiar(ahora)
                except Exception as e:  # noqa: BLE001
                    registro.exception("al cambiar la presencia: %s", e)
            parar.wait(cada_s)

    hilo = threading.Thread(target=bucle, name="botonera-presencia", daemon=True)
    hilo.start()
    return hilo
