"""Dónde está el zip de la Botonera, para ofrecerlo desde el panel.

Desde el código fuente es ``dist/Botonera-<versión>.zip`` en la raíz del
proyecto (lo deja ``construir_botonera.py``). Desde el propio ejecutable, es
el zip que haya junto a su carpeta: así un PC que ya tiene la Botonera puede
repartirla al siguiente.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import __version__

#: Una carpeta en un zip, con la versión en el nombre para saber qué se instaló.
NOMBRE_EXE = f"Botonera-{__version__}.zip"


def ruta_ejecutable() -> Path | None:
    if getattr(sys, "frozen", False):
        candidato = Path(sys.executable).resolve().parent.parent / NOMBRE_EXE
    else:
        candidato = Path(__file__).resolve().parents[2] / "dist" / NOMBRE_EXE
    return candidato if candidato.is_file() else None


def resumen_ejecutable() -> dict[str, Any]:
    ruta = ruta_ejecutable()
    if ruta is None:
        return {"disponible": False, "nombre": NOMBRE_EXE, "como": "python construir_botonera.py"}
    tamano = ruta.stat().st_size
    return {"disponible": True, "nombre": NOMBRE_EXE, "megas": round(tamano / 1_048_576, 1), "bytes": tamano}
