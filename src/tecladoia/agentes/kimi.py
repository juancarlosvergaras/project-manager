"""Adaptador de Kimi CLI.

Kimi decide con ``default_yolo`` en ``~/.kimi/config.toml``: activado equivale a
ejecutar sin preguntar. La palanca lo enciende y lo apaga, y además el enganche
``PreToolUse`` frena la acción cuando toca.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from ..modelo import Decision, EstadoIA, Veredicto
from .base import (
    MARCA,
    AgenteIA,
    EventoEnganche,
    bloque_marcado,
    motivo_legible,
    orden_enganche,
    quitar_bloque_marcado,
    respaldar,
)

_PATRON_YOLO = re.compile(r"^\s*default_yolo\s*=.*$", re.MULTILINE)


class AgenteKimi(AgenteIA):
    id = "kimi"
    nombre = "Kimi CLI"
    url_documentacion = "https://github.com/MoonshotAI/kimi-cli"

    eventos = (
        EventoEnganche("KimiSessionStart", "SessionStart", EstadoIA.SESION_INICIADA),
        EventoEnganche("KimiUserPromptSubmit", "UserPromptSubmit", EstadoIA.PETICION_ENVIADA),
        EventoEnganche("KimiPreToolUse", "PreToolUse", EstadoIA.HERRAMIENTA_EN_CURSO, 20, permiso=True),
        EventoEnganche("KimiPostToolUse", "PostToolUse", EstadoIA.HERRAMIENTA_TERMINADA),
        EventoEnganche("KimiNotification", "Notification", EstadoIA.NOTIFICACION),
        # «Stop» es TERMINAR el turno, no detenerse. No existe ningun evento
        # «TaskCompleted»: esto es lo unico que avisa de que ha acabado. Con
        # DETENIDO —que ademas es el estado de reposo— terminar equivalia a
        # apagar la barra y el verde no se encendia jamas.
        EventoEnganche("KimiStop", "Stop", EstadoIA.TAREA_COMPLETADA),
        EventoEnganche("KimiSessionEnd", "SessionEnd", EstadoIA.SESION_FINALIZADA),
    )

    @classmethod
    def ruta_config(cls) -> Path:
        return Path.home() / ".kimi" / "config.toml"

    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        if not evento.permiso or veredicto is None:
            return {}
        if veredicto.decision is Decision.PERMITIR:
            return {}
        return {
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "permissionDecisionReason": motivo_legible(veredicto),
            }
        }

    @classmethod
    def sincronizar_palanca(cls, automatica: bool) -> Optional[str]:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return None
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            return None
        valor = "true" if automatica else "false"
        linea = f"default_yolo = {valor}  # TecladoIA: sigue la palanca (usa /reload en Kimi)"
        if _PATRON_YOLO.search(texto):
            if re.search(rf"^\s*default_yolo\s*=\s*{valor}\b", texto, re.MULTILINE):
                return None
            texto = _PATRON_YOLO.sub(linea, texto, count=1)
        else:
            primera_seccion = texto.find("\n[")
            if primera_seccion < 0:
                texto = texto.rstrip() + "\n" + linea + "\n"
            else:
                texto = texto[:primera_seccion] + "\n" + linea + texto[primera_seccion:]
        try:
            ruta.write_text(texto, encoding="utf-8")
        except OSError:
            return None
        return f"default_yolo = {valor} en {ruta}"

    @classmethod
    def instalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        mensajes: list[str] = []
        if copia := respaldar(ruta):
            mensajes.append(f"Copia de seguridad en {copia}")
        texto = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
        texto = quitar_bloque_marcado(texto)
        lineas = ["[hooks]"]
        for evento in cls.eventos:
            orden = orden_enganche(cls.id, evento.interno).replace('"', '\\"')
            lineas.append(f'{evento.externo} = [{{ type = "command", command = "{orden}", '
                          f"timeout = {evento.tiempo_limite} }}]")
        cuerpo = bloque_marcado("\n".join(lineas))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text((texto.rstrip() + "\n\n" if texto.strip() else "") + cuerpo, encoding="utf-8")
        mensajes.append(f"{len(cls.eventos)} eventos registrados en {ruta}")
        return mensajes

    @classmethod
    def desinstalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return [f"No hay configuración de Kimi en {ruta}"]
        texto = ruta.read_text(encoding="utf-8")
        if MARCA not in texto and "TecladoIA" not in texto:
            return ["Kimi no tenía enganches de TecladoIA"]
        respaldar(ruta)
        ruta.write_text(quitar_bloque_marcado(texto), encoding="utf-8")
        return [f"Bloque de TecladoIA retirado de {ruta}"]
