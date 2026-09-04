"""Dónde está el ejecutable de SikaiMini, para ofrecerlo desde el panel.

Desde el código fuente es ``dist/SikaiMini.exe`` en la raíz del proyecto (lo
deja ``construir_sikaimini.py``). Desde el propio ejecutable, es él mismo: así
un PC que ya tiene SikaiMini instalado puede repartirlo al siguiente.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

NOMBRE_EXE = "SikaiMini.zip"  # una carpeta en un zip; ver construir_sikaimini.py


def ruta_ejecutable() -> Path | None:
    """El zip para repartir. Desde el código, en ``dist/``; desde el propio
    programa instalado, el ``SikaiMini.zip`` que haya junto a su carpeta, si lo hay."""
    if getattr(sys, "frozen", False):
        candidato = Path(sys.executable).resolve().parent.parent / NOMBRE_EXE
    else:
        candidato = Path(__file__).resolve().parents[2] / "dist" / NOMBRE_EXE
    return candidato if candidato.is_file() else None


def resumen_ejecutable() -> dict[str, Any]:
    ruta = ruta_ejecutable()
    if ruta is None:
        return {"disponible": False, "nombre": NOMBRE_EXE, "como": "python construir_sikaimini.py"}
    tamano = ruta.stat().st_size
    return {"disponible": True, "nombre": NOMBRE_EXE, "megas": round(tamano / 1_048_576, 1), "bytes": tamano}
