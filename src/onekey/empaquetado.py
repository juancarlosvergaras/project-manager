"""Dónde está el instalador de OneKey, para ofrecerlo desde el panel.

Desde el código fuente es ``dist/OneKey-<versión>.zip`` (lo deja
``construir_onekey.py``). Desde el propio programa instalado, el zip que haya
junto a su carpeta, si lo hay: así un PC que ya tiene OneKey puede repartirlo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import __version__

#: Una carpeta en un zip, con la versión en el nombre.
NOMBRE_EXE = f"OneKey-{__version__}.zip"


def ruta_ejecutable() -> Path | None:
    if getattr(sys, "frozen", False):
        candidato = Path(sys.executable).resolve().parent.parent / NOMBRE_EXE
    else:
        candidato = Path(__file__).resolve().parents[2] / "dist" / NOMBRE_EXE
    return candidato if candidato.is_file() else None


def resumen_ejecutable() -> dict[str, Any]:
    ruta = ruta_ejecutable()
    if ruta is None:
        return {"disponible": False, "nombre": NOMBRE_EXE, "como": "python construir_onekey.py"}
    tamano = ruta.stat().st_size
    return {"disponible": True, "nombre": NOMBRE_EXE, "megas": round(tamano / 1_048_576, 1), "bytes": tamano}
