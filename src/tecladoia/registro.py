"""Registro de eventos y bitácora de auditoría.

Cada decisión de aprobación se guarda como una línea JSON. Así se puede
responder después a la pregunta que el proyecto original dejaba sin respuesta:
*¿qué aprobó el teclado por mí y por qué?*
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .config import ruta_bitacora

_FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_NIVELES = {
    "critico": logging.CRITICAL,
    "error": logging.ERROR,
    "aviso": logging.WARNING,
    "info": logging.INFO,
    "detalle": logging.DEBUG,
}


def configurar(nivel: str = "info") -> None:
    """Prepara el registro de consola."""
    entorno = os.environ.get("TECLADOIA_NIVEL", "").lower()
    elegido = _NIVELES.get(entorno or nivel.lower(), logging.INFO)
    logging.basicConfig(level=elegido, format=_FORMATO, datefmt="%H:%M:%S")


def obtener(nombre: str) -> logging.Logger:
    return logging.getLogger(f"tecladoia.{nombre}")


def anotar(entrada: dict[str, Any], ruta: Path | None = None) -> None:
    """Añade una línea a la bitácora de auditoría."""
    ruta = ruta or ruta_bitacora()
    entrada = {"instante": datetime.now().astimezone().isoformat(timespec="seconds"), **entrada}
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except OSError as error:  # la bitácora nunca debe tumbar una aprobación
        obtener("bitacora").warning("No se pudo escribir la bitácora: %s", error)


def leer_bitacora(limite: int = 50, ruta: Path | None = None) -> list[dict[str, Any]]:
    """Devuelve las últimas ``limite`` entradas, de la más reciente a la más antigua."""
    ruta = ruta or ruta_bitacora()
    if not ruta.exists():
        return []
    entradas: list[dict[str, Any]] = []
    for linea in _lineas_finales(ruta, limite):
        try:
            entradas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    entradas.reverse()
    return entradas


def _lineas_finales(ruta: Path, limite: int) -> Iterator[str]:
    with ruta.open("r", encoding="utf-8", errors="replace") as archivo:
        cola: list[str] = []
        for linea in archivo:
            linea = linea.strip()
            if not linea:
                continue
            cola.append(linea)
            if len(cola) > limite:
                cola.pop(0)
    yield from cola
