"""Adaptador de Claude Code."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..modelo import Decision, EstadoIA, Veredicto
from .base import (
    AgenteIA,
    EventoEnganche,
    escribir_json,
    fusionar_enganches,
    leer_json,
    limpiar_enganches,
    motivo_legible,
    respaldar,
)

#: Claude Code decide el permiso con «allow», «deny» o «escalate»; esta última
#: es la que muestra el aviso a la persona.
_DECISION = {
    Decision.PERMITIR: "allow",
    Decision.DENEGAR: "deny",
    Decision.PREGUNTAR: "escalate",
}


class AgenteClaude(AgenteIA):
    id = "claude"
    nombre = "Claude Code"
    url_documentacion = "https://code.claude.com/docs/en/hooks"

    eventos = (
        EventoEnganche("SessionStart", "SessionStart", EstadoIA.SESION_INICIADA),
        EventoEnganche("UserPromptSubmit", "UserPromptSubmit", EstadoIA.PETICION_ENVIADA),
        EventoEnganche("PreToolUse", "PreToolUse", EstadoIA.HERRAMIENTA_EN_CURSO, 20, filtro="*"),
        EventoEnganche(
            "PermissionRequest",
            "PermissionRequest",
            EstadoIA.ESPERANDO_APROBACION,
            60,
            permiso=True,
            filtro="*",
        ),
        EventoEnganche("PostToolUse", "PostToolUse", EstadoIA.HERRAMIENTA_TERMINADA, filtro="*"),
        EventoEnganche("Notification", "Notification", EstadoIA.NOTIFICACION),
        EventoEnganche("TaskCompleted", "TaskCompleted", EstadoIA.TAREA_COMPLETADA),
        # «Stop» es TERMINAR el turno, no detenerse. No existe ningun evento
        # «TaskCompleted»: esto es lo unico que avisa de que ha acabado. Con
        # DETENIDO —que ademas es el estado de reposo— terminar equivalia a
        # apagar la barra y el verde no se encendia jamas.
        EventoEnganche("Stop", "Stop", EstadoIA.TAREA_COMPLETADA),
        EventoEnganche("SessionEnd", "SessionEnd", EstadoIA.SESION_FINALIZADA),
    )

    @classmethod
    def ruta_config(cls) -> Path:
        return Path.home() / ".claude" / "settings.json"

    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        if evento.permiso and veredicto is not None:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": _DECISION[veredicto.decision],
                    "permissionDecisionReason": motivo_legible(veredicto),
                }
            }
        # En PreToolUse solo intervenimos para frenar lo que una regla prohíbe;
        # el resto del flujo lo decide PermissionRequest.
        if (
            evento.interno == "PreToolUse"
            and veredicto is not None
            and veredicto.decision is Decision.DENEGAR
        ):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": motivo_legible(veredicto),
                }
            }
        return {}

    @classmethod
    def instalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        mensajes: list[str] = []
        if copia := respaldar(ruta):
            mensajes.append(f"Copia de seguridad en {copia}")
        ajustes = leer_json(ruta)
        seccion = ajustes.setdefault("hooks", {})
        if not isinstance(seccion, dict):
            seccion = {}
            ajustes["hooks"] = seccion
        fusionar_enganches(seccion, cls.eventos, cls.id)
        escribir_json(ruta, ajustes)
        mensajes.append(f"{len(cls.eventos)} eventos registrados en {ruta}")
        return mensajes

    @classmethod
    def desinstalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return [f"No hay configuración de Claude Code en {ruta}"]
        ajustes = leer_json(ruta)
        seccion = ajustes.get("hooks")
        if not isinstance(seccion, dict):
            return ["Claude Code no tenía enganches de TecladoIA"]
        quitados = limpiar_enganches(seccion)
        if not seccion:
            ajustes.pop("hooks", None)
        escribir_json(ruta, ajustes)
        return [f"{quitados} enganches retirados de {ruta}"]
