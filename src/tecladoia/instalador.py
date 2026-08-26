"""Instalación y revisión de los enganches en cada programa de IA."""

from __future__ import annotations

from typing import Iterable, Optional

from . import agentes
from .agentes.base import AgenteIA


def _resolver(nombres: Optional[Iterable[str]]) -> list[type[AgenteIA]]:
    if not nombres:
        return [a for a in agentes.AGENTES if a.id != "generico"]
    elegidos: list[type[AgenteIA]] = []
    for nombre in nombres:
        agente = agentes.obtener(nombre)
        if agente is None:
            raise ValueError(f"Agente desconocido: {nombre}")
        elegidos.append(agente)
    return elegidos


def instalar(nombres: Optional[Iterable[str]] = None) -> dict[str, list[str]]:
    """Instala los enganches. Sin argumentos, en todos los agentes conocidos."""
    resultado: dict[str, list[str]] = {}
    for agente in _resolver(nombres):
        try:
            resultado[agente.nombre] = agente.instalar()
        except Exception as error:  # noqa: BLE001 - un agente no debe frenar al resto
            resultado[agente.nombre] = [f"Error: {error}"]
    return resultado


def desinstalar(nombres: Optional[Iterable[str]] = None) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for agente in _resolver(nombres):
        try:
            resultado[agente.nombre] = agente.desinstalar()
        except Exception as error:  # noqa: BLE001
            resultado[agente.nombre] = [f"Error: {error}"]
    return resultado


def revisar() -> list[dict]:
    """Estado de cada agente: si está instalado y dónde vive su configuración."""
    informe: list[dict] = []
    for agente in agentes.AGENTES:
        try:
            ruta = agente.ruta_config()
            instalado = agente.instalado()
        except Exception:  # noqa: BLE001
            ruta, instalado = None, False
        informe.append(
            {
                "id": agente.id,
                "nombre": agente.nombre,
                "config": str(ruta) if ruta else "—",
                "existe_config": bool(ruta and ruta.exists()),
                "instalado": instalado,
                "eventos": len(agente.eventos),
                "permisos": sum(1 for e in agente.eventos if e.permiso),
            }
        )
    return informe
