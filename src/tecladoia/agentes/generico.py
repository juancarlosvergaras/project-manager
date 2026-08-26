"""Adaptador genérico para cualquier programa de IA.

Sirve para incluir herramientas que aún no tienen adaptador propio. No escribe
en la configuración de nadie: se invoca a mano desde el enganche, script o
integración que la persona ya tenga::

    tecladoia enganche generico PreToolUse --herramienta Bash --comando "git push"

Devuelve un JSON neutro con la decisión y el motivo, para que cualquiera lo
interprete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..config import directorio_base
from ..modelo import EstadoIA, Veredicto
from .base import AgenteIA, EventoEnganche, motivo_legible


class AgenteGenerico(AgenteIA):
    id = "generico"
    nombre = "Agente genérico"

    eventos = (
        EventoEnganche("SesionInicio", "SesionInicio", EstadoIA.SESION_INICIADA),
        EventoEnganche("PeticionEnviada", "PeticionEnviada", EstadoIA.PETICION_ENVIADA),
        EventoEnganche("PreToolUse", "PreToolUse", EstadoIA.HERRAMIENTA_EN_CURSO, 20, permiso=True),
        EventoEnganche("PostToolUse", "PostToolUse", EstadoIA.HERRAMIENTA_TERMINADA),
        EventoEnganche("Aviso", "Aviso", EstadoIA.NOTIFICACION),
        EventoEnganche("TareaCompletada", "TareaCompletada", EstadoIA.TAREA_COMPLETADA),
        EventoEnganche("Detenido", "Detenido", EstadoIA.DETENIDO),
        EventoEnganche("SesionFin", "SesionFin", EstadoIA.SESION_FINALIZADA),
    )

    @classmethod
    def ruta_config(cls) -> Path:
        return directorio_base() / "generico.json"

    @classmethod
    def instalado(cls) -> bool:
        return True  # no necesita instalación

    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        if veredicto is None:
            return {"ok": True, "decision": None}
        return {
            "ok": True,
            "decision": veredicto.decision.value,
            "automatica": veredicto.automatica,
            "motivo": veredicto.motivo.value,
            "explicacion": motivo_legible(veredicto),
            "palanca": veredicto.palanca,
        }

    @classmethod
    def instalar(cls) -> list[str]:
        return [
            "El agente genérico no toca ninguna configuración.",
            "Llama a «tecladoia enganche generico <evento>» desde tu propio script.",
        ]

    @classmethod
    def desinstalar(cls) -> list[str]:
        return ["El agente genérico no deja nada instalado."]
