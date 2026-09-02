"""Dónde está el ejecutable de MiniMic, para ofrecerlo desde el panel.

Desde el código fuente es ``dist/MiniMic.exe`` en la raíz del proyecto (lo
deja ``construir_minimic.py``). Desde el propio ejecutable, es él mismo: así
un PC que ya tiene MiniMic instalado puede repartirlo al siguiente.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

NOMBRE_EXE = "MiniMic.exe"


def ruta_ejecutable() -> Path | None:
    if getattr(sys, "frozen", False):
        propio = Path(sys.executable).resolve()
        return propio if propio.is_file() else None
    candidato = Path(__file__).resolve().parents[2] / "dist" / NOMBRE_EXE
    return candidato if candidato.is_file() else None


def resumen_ejecutable() -> dict[str, Any]:
    ruta = ruta_ejecutable()
    if ruta is None:
        return {"disponible": False, "nombre": NOMBRE_EXE, "como": "python construir_minimic.py"}
    tamano = ruta.stat().st_size
    return {"disponible": True, "nombre": NOMBRE_EXE, "megas": round(tamano / 1_048_576, 1), "bytes": tamano}
