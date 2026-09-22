"""Construye SikaiMini: una carpeta con el ejecutable y Python al lado, en un zip.

``python construir_sikaimini.py`` deja ``dist/SikaiMini/SikaiMini.exe`` y
``dist/SikaiMini.zip``. Misma receta que ``construir_exe.py`` (TecladoIA) salvo
en una cosa: **carpeta, no un solo archivo**. El ``.exe`` de un solo archivo
se autoextrae al arrancar, y eso es justo lo que la heurística de Defender
(«Trojan:Win32/Bearfoos.A!ml») marca en cuanto llega descargado: el mismo
archivo escaneado en disco estaba limpio. Con la carpeta no hay
autoextracción y no salta.

* **La carpeta ``web`` de SikaiMini viaja dentro**, en la misma ruta relativa;
  sin ella el panel sale en blanco.
* **``comtypes``, ``pycaw`` y ``hid`` se incluyen a mano**: se importan dentro
  de funciones y PyInstaller no siempre los ve. Sin ``hid`` el ejecutable
  arranca y nunca encuentra el teclado; sin ``pycaw`` nunca adopta el micrófono.
* No lleva ``winrt`` ni ``bleak``: SikaiMini no usa Bluetooth.
* **``minimic`` va dentro**: SikaiMini importa su protocolo y su canal HID.
"""

from __future__ import annotations

import sys
from pathlib import Path

from construir_comun import construir_carpeta

RAIZ = Path(__file__).resolve().parent

OCULTOS = [
    "hid",
    "comtypes", "comtypes.client", "comtypes.automation",
    "pycaw", "pycaw.utils", "pycaw.constants", "pycaw.api.policyconfig", "pycaw.api.mmdeviceapi",
    "pycaw.api.mmdeviceapi.depend", "pycaw.api.mmdeviceapi.depend.structures",
    "tecladoia.dictado", "tecladoia.cuadro_de_texto", "tecladoia.sonido", "tecladoia.sucesos", "tecladoia.registro",
    # SikaiMini se apoya en MiniMic (protocolo, canal HID, micrófono, ficha de programas).
    "minimic", "minimic.protocolo", "minimic.dispositivo", "minimic.config",
]

LEEME = """SikaiMini

Deja esta carpeta entera donde quieras tenerla (por ejemplo en Documentos)
y abre SikaiMini.exe. Hace la instalación guiada: crea la tarea que lo arranca
con Windows (con el ejecutable *Servicio.exe, que no abre ninguna ventana)
y lo pone en marcha. El panel queda en http://127.0.0.1:8772

No muevas ni borres la carpeta _internal: es el Python que lleva dentro.
"""


def construir() -> int:
    """Dos ejecutables sobre el mismo Python: ``SikaiMini.exe`` (instalación guiada,
    con consola) y ``SikaiMiniServicio.exe`` (el servicio, sin ventana). Ver
    ``construir_comun.py``."""
    sys.path.insert(0, str(RAIZ / "src"))
    from sikaimini.empaquetado import NOMBRE_EXE

    return construir_carpeta(
        nombre="SikaiMini",
        lanzador="lanzador_sikaimini.py",
        datas=[("src/sikaimini/web", "sikaimini/web")],
        ocultos=OCULTOS,
        leeme=LEEME,
        nombre_zip=NOMBRE_EXE,
    )


if __name__ == "__main__":
    raise SystemExit(construir())
