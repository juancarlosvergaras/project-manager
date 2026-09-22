"""Construye la Botonera: una carpeta con el ejecutable y Python al lado, en un zip.

``python construir_botonera.py`` deja ``dist/Botonera/Botonera.exe`` y
``dist/Botonera-<versión>.zip`` (más la copia ``Botonera.zip`` para los enlaces
fijos). Misma receta que SikaiMini: **carpeta, no un solo archivo**, para que
Defender no marque la autoextracción.

* **La carpeta ``web`` viaja dentro**, en la misma ruta relativa.
* **``hid`` y ``comtypes`` se incluyen a mano**: se importan dentro de
  funciones. Sin ``hid`` el ejecutable arranca y nunca encuentra el teclado;
  sin ``comtypes`` la tecla de dictado no encuentra el botón de Claude.
* **``minimic``, ``sikaimini`` y ``tecladoia`` van dentro**: la Botonera toma
  de ellos el canal HID, las tablas de teclas, el túnel y el dictado.
"""

from __future__ import annotations

import sys
from pathlib import Path

from construir_comun import construir_carpeta

RAIZ = Path(__file__).resolve().parent

OCULTOS = [
    "hid",
    "comtypes", "comtypes.client", "comtypes.automation",
    "tecladoia.dictado", "tecladoia.cuadro_de_texto", "tecladoia.sonido", "tecladoia.sucesos", "tecladoia.registro",
    "tecladoia.enfoque", "tecladoia.microfono_propio",
    "minimic", "minimic.protocolo", "minimic.dispositivo", "minimic.config", "minimic.tunel",
    "sikaimini.protocolo",
    "botonera.asistente", "botonera.lanzador", "botonera.escucha",
]

LEEME = """Botonera

Deja esta carpeta entera donde quieras tenerla (por ejemplo en Documentos)
y abre Botonera.exe. Hace la instalación guiada: crea la tarea que lo arranca
con Windows (con el ejecutable *Servicio.exe, que no abre ninguna ventana)
y lo pone en marcha. El panel queda en http://127.0.0.1:8773

No muevas ni borres la carpeta _internal: es el Python que lleva dentro.
"""


def construir() -> int:
    """Dos ejecutables sobre el mismo Python: ``Botonera.exe`` (instalación guiada,
    con consola) y ``BotoneraServicio.exe`` (el servicio, sin ventana). Ver
    ``construir_comun.py``."""
    sys.path.insert(0, str(RAIZ / "src"))
    from botonera.empaquetado import NOMBRE_EXE

    return construir_carpeta(
        nombre="Botonera",
        lanzador="lanzador_botonera.py",
        datas=[("src/botonera/web", "botonera/web")],
        ocultos=OCULTOS,
        leeme=LEEME,
        nombre_zip=NOMBRE_EXE,
    )


if __name__ == "__main__":
    raise SystemExit(construir())
