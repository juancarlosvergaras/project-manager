"""Construye OneKey: una carpeta con dos ejecutables y Python al lado, en un zip.

``python construir_onekey.py`` deja ``dist/OneKey/OneKey.exe`` (instalación
guiada, con consola), ``dist/OneKey/OneKeyServicio.exe`` (el servicio, sin
ventana) y ``dist/OneKey-<versión>.zip``. La receta es la común de
``construir_comun.py``.

* **La carpeta ``web`` de OneKey viaja dentro**; sin ella el panel sale en blanco.
* **``comtypes``, ``pycaw`` y ``hid`` se incluyen a mano**: se importan dentro
  de funciones y PyInstaller no siempre los ve.
* **``minimic`` y ``tecladoia`` van dentro**: OneKey toma de ahí el botón, el
  micrófono, el dictado y el túnel.
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
    "tecladoia.tunel", "tecladoia.microfono_propio", "tecladoia.enfoque",
    "minimic", "minimic.boton", "minimic.dispositivo", "minimic.config", "minimic.protocolo",
]

LEEME = """OneKey

Deja esta carpeta entera donde quieras tenerla (por ejemplo en Documentos)
y abre OneKey.exe. Hace la instalación guiada: crea la tarea que lo arranca
con Windows (con OneKeyServicio.exe, que no abre ninguna ventana) y lo pone
en marcha. El panel queda en http://127.0.0.1:8774

Empareja el botón «AI_VOICE» en Configuración > Bluetooth. Pulsa el botón:
se abre el dictado en el programa que elijas. Vuelve a pulsarlo: el texto entra.

No muevas ni borres la carpeta _internal: es el Python que lleva dentro.
"""


def construir() -> int:
    sys.path.insert(0, str(RAIZ / "src"))
    from onekey.empaquetado import NOMBRE_EXE

    return construir_carpeta(
        nombre="OneKey",
        lanzador="lanzador_onekey.py",
        datas=[("src/onekey/web", "onekey/web")],
        ocultos=OCULTOS,
        leeme=LEEME,
        nombre_zip=NOMBRE_EXE,
    )


if __name__ == "__main__":
    raise SystemExit(construir())
