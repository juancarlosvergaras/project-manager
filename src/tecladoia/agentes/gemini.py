"""Adaptador de Gemini CLI.

Gemini nombra sus eventos ``BeforeTool`` / ``AfterTool`` y solo entiende
«allow», «deny» y «block». No hay un valor para «pregúntale a la persona», pero
sí un comportamiento equivalente: si el enganche no dice nada, Gemini muestra su
propia confirmación. Eso es justo lo que hace falta con la palanca en manual, y
por eso este adaptador calla en vez de bloquear.
"""

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


class AgenteGemini(AgenteIA):
    id = "gemini"
    nombre = "Gemini CLI"
    url_documentacion = "https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md"

    eventos = (
        EventoEnganche("GeminiSessionStart", "SessionStart", EstadoIA.SESION_INICIADA),
        EventoEnganche("GeminiBeforeTool", "BeforeTool", EstadoIA.HERRAMIENTA_EN_CURSO, 20, permiso=True, filtro=".*"),
        EventoEnganche("GeminiAfterTool", "AfterTool", EstadoIA.HERRAMIENTA_TERMINADA, filtro=".*"),
        EventoEnganche("GeminiNotification", "Notification", EstadoIA.NOTIFICACION),
        EventoEnganche("GeminiSessionEnd", "SessionEnd", EstadoIA.SESION_FINALIZADA),
    )

    @classmethod
    def ruta_config(cls) -> Path:
        return Path.home() / ".gemini" / "settings.json"

    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        if not evento.permiso or veredicto is None:
            return {}
        if veredicto.decision is Decision.PERMITIR:
            return {"decision": "allow"}
        if veredicto.decision is Decision.DENEGAR:
            return {"decision": "deny", "reason": motivo_legible(veredicto)}
        # Sin decisión: Gemini enseña su confirmación de siempre.
        return {"systemMessage": motivo_legible(veredicto)}

    @classmethod
    def instalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        mensajes: list[str] = []
        if copia := respaldar(ruta):
            mensajes.append(f"Copia de seguridad en {copia}")
        datos = leer_json(ruta)
        seccion = datos.setdefault("hooks", {})
        if not isinstance(seccion, dict):
            seccion = {}
            datos["hooks"] = seccion
        # Gemini mide el tiempo límite en milisegundos.
        fusionar_enganches(seccion, cls.eventos, cls.id, tiempo_en_ms=True)
        escribir_json(ruta, datos)
        mensajes.append(f"{len(cls.eventos)} eventos registrados en {ruta}")
        return mensajes

    @classmethod
    def desinstalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return [f"No hay configuración de Gemini CLI en {ruta}"]
        datos = leer_json(ruta)
        seccion = datos.get("hooks")
        if not isinstance(seccion, dict):
            return ["Gemini CLI no tenía enganches de TecladoIA"]
        quitados = limpiar_enganches(seccion)
        if not seccion:
            datos.pop("hooks", None)
        escribir_json(ruta, datos)
        return [f"{quitados} enganches retirados de {ruta}"]
