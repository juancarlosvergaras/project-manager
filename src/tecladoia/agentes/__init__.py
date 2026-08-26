"""Registro de los programas de IA que TecladoIA sabe manejar."""

from __future__ import annotations

from typing import Optional

from .base import AgenteIA, EventoEnganche
from .claude import AgenteClaude
from .codex import AgenteCodex
from .cursor import AgenteCursor
from .gemini import AgenteGemini
from .generico import AgenteGenerico
from .kimi import AgenteKimi

AGENTES: tuple[type[AgenteIA], ...] = (
    AgenteClaude,
    AgenteCodex,
    AgenteCursor,
    AgenteKimi,
    AgenteGemini,
    AgenteGenerico,
)

POR_ID: dict[str, type[AgenteIA]] = {a.id: a for a in AGENTES}

__all__ = [
    "AGENTES",
    "POR_ID",
    "AgenteIA",
    "EventoEnganche",
    "obtener",
    "buscar_evento",
]


def obtener(identificador: str) -> Optional[type[AgenteIA]]:
    """Busca un agente por su identificador, sin distinguir mayúsculas."""
    return POR_ID.get((identificador or "").strip().lower())


def buscar_evento(interno: str) -> Optional[tuple[type[AgenteIA], EventoEnganche]]:
    """Localiza a qué agente pertenece un nombre de evento interno.

    Los nombres internos son únicos entre los agentes con adaptador propio
    (``CodexPreToolUse``, ``KimiPreToolUse``…), así que sirve como respaldo
    cuando el enganche llega sin decir de quién es. El agente genérico se queda
    fuera a propósito: usa nombres cortos y legibles (``PreToolUse``) que solo
    tienen sentido cuando se le nombra de forma explícita.
    """
    for agente in AGENTES:
        if agente.id == "generico":
            continue
        evento = agente.evento(interno)
        if evento is not None:
            return agente, evento
    return None
