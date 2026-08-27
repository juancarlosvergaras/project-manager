"""Registro de los programas de IA que TecladoIA sabe manejar."""

from __future__ import annotations

from typing import Optional

from .base import AgenteIA, EventoEnganche
from .chatgpt import AgenteChatGPT
from .claude import AgenteClaude
from .codex import AgenteCodex
from .cursor import AgenteCursor
from .gemini import AgenteGemini
from .generico import AgenteGenerico
from .kimi import AgenteKimi

#: Los que se ofrecen en el panel, en el orden en que se enseñan. ChatGPT va
#: el segundo porque es el dueño del modo 2.
#:
#: **Codex CLI no está aquí a propósito.** Su adaptador se conserva —funciona,
#: y quien lo use puede pedirlo por su nombre— pero no se ofrece ni se instala
#: por omisión: quien tiene la aplicación de ChatGPT no tiene Codex, y ver en
#: la lista un programa que no existe en el equipo solo confunde.
AGENTES: tuple[type[AgenteIA], ...] = (
    AgenteClaude,
    AgenteChatGPT,
    AgenteCursor,
    AgenteKimi,
    AgenteGemini,
    AgenteGenerico,
)

#: Todos los que TecladoIA sabe manejar, ofrecidos o no. Sirve para resolver
#: por nombre y para que ``buscar_evento`` siga reconociendo los eventos de
#: Codex si alguien los tiene puestos de antes.
CONOCIDOS: tuple[type[AgenteIA], ...] = AGENTES + (AgenteCodex,)

POR_ID: dict[str, type[AgenteIA]] = {a.id: a for a in CONOCIDOS}

__all__ = [
    "AGENTES",
    "CONOCIDOS",
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
    for agente in CONOCIDOS:
        if agente.id == "generico":
            continue
        evento = agente.evento(interno)
        if evento is not None:
            return agente, evento
    return None
