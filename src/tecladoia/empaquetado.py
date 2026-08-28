"""Genera el paquete que se descarga desde la web para usarlo en local.

El panel puede correr en un servidor, pero el teclado está donde estás tú: el
Bluetooth no viaja por Internet. Así que la web ofrece descargar la aplicación
entera —el mismo código, sin recortes— para instalarla en el equipo que tiene
el teclado cerca.

El paquete se arma al vuelo, en memoria, a partir del código que está corriendo.
No hay que compilar nada ni mantener un fichero aparte que se quede viejo: lo
que te descargas es exactamente la versión que estás viendo.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator

#: Carpetas y sufijos que nunca entran en el paquete.
_EXCLUIR_CARPETAS = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache", "dist", "build"}
_EXCLUIR_SUFIJOS = {".pyc", ".pyo", ".log"}

_INSTRUCCIONES = r"""TecladoIA — instalación en tu equipo
=====================================

Este paquete es la aplicación completa. Se instala en el ordenador que tiene
el teclado AhaKey cerca, porque el Bluetooth no viaja por Internet.

Necesitas Python 3.10 o posterior. Nada más.


1. Instalar
-----------

    pip install -e .

Y si quieres hablar con el teclado real por Bluetooth:

    pip install -e ".[ble]"


2. Probar sin teclado
---------------------

    tecladoia probar

Recorre el flujo completo con un teclado simulado y no toca nada de tu equipo.


3. Poner los enganches en tus programas de IA
---------------------------------------------

    tecladoia instalar

Detecta cuáles tienes (Codex, Claude Code, Cursor, Kimi, Gemini) y añade los
enganches conservando los que ya tuvieras. Hace copia de seguridad antes.


4. Arrancar
-----------

    tecladoia servicio

Y abre http://127.0.0.1:8770 en el navegador. Si no tienes el teclado a mano:

    tecladoia servicio --sin-teclado


Cómo decide
-----------

Las reglas de la configuración mandan sobre lo destructivo (rm -rf, mkfs,
dd if=...) incluso con la palanca en automático. Si la palanca no se puede
leer, nunca se aprueba solo: la decisión vuelve a ti.

La configuración vive en:
  Windows        %APPDATA%\TecladoIA\config.json
  macOS y Linux  ~/.tecladoia/config.json
"""


def _raiz_del_proyecto() -> Path:
    """Carpeta que contiene ``src/`` cuando se trabaja desde el repositorio."""
    aqui = Path(__file__).resolve()
    candidata = aqui.parent.parent.parent  # .../src/tecladoia/x.py -> raíz
    return candidata if (candidata / "src").is_dir() else aqui.parent.parent


def _interesa(ruta: Path) -> bool:
    if any(parte in _EXCLUIR_CARPETAS for parte in ruta.parts):
        return False
    return ruta.suffix.lower() not in _EXCLUIR_SUFIJOS


def _archivos(raiz: Path) -> Iterator[tuple[Path, str]]:
    """Pares (ruta en disco, nombre dentro del zip)."""
    paquete = raiz / "src" / "tecladoia"
    if paquete.is_dir():
        for archivo in sorted(paquete.rglob("*")):
            if archivo.is_file() and _interesa(archivo.relative_to(raiz)):
                yield archivo, str(archivo.relative_to(raiz)).replace("\\", "/")
    for suelto in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):
        camino = raiz / suelto
        if camino.is_file():
            yield camino, suelto


def construir_zip(raiz: Path | None = None) -> bytes:
    """Devuelve el paquete completo como bytes, listo para servir."""
    raiz = raiz or _raiz_del_proyecto()
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as paquete:
        for archivo, nombre in _archivos(raiz):
            paquete.write(archivo, f"tecladoia/{nombre}")
        paquete.writestr("tecladoia/INSTALAR.txt", _INSTRUCCIONES)
    return memoria.getvalue()


def resumen(raiz: Path | None = None) -> dict:
    """Datos del paquete para enseñarlos antes de descargar."""
    datos = construir_zip(raiz)
    with zipfile.ZipFile(io.BytesIO(datos)) as paquete:
        archivos = len(paquete.namelist())
    return {"bytes": len(datos), "archivos": archivos, "nombre": "tecladoia.zip"}


def ruta_ejecutable(raiz: Path | None = None) -> Path | None:
    """Dónde está TecladoIA.exe, si se ha construido.

    Es opcional a propósito: quien trabaja desde el código no lo necesita y
    construirlo tarda un par de minutos. Si no está, el panel ofrece el zip y
    ya está, en vez de enseñar un botón que da error al pulsarlo.
    """
    raiz = raiz or Path(__file__).resolve().parent.parent.parent
    exe = raiz / "dist" / "TecladoIA.exe"
    return exe if exe.is_file() else None


def resumen_ejecutable(raiz: Path | None = None) -> dict:
    """Datos del ejecutable para la pestaña de descarga."""
    exe = ruta_ejecutable(raiz)
    if exe is None:
        return {"hay": False}
    return {
        "hay": True,
        "bytes": exe.stat().st_size,
        "nombre": "TecladoIA.exe",
    }


__all__ = ["construir_zip", "resumen", "ruta_ejecutable", "resumen_ejecutable"]
