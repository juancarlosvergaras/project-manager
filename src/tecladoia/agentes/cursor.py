"""Adaptador de Cursor (CLI y agente del editor).

Cursor solo admite «allow» o «deny»: no tiene un estado intermedio de
«pregúntale a la persona». Con la palanca en manual devolvemos ``deny`` con un
motivo legible, que es lo que hace también el proyecto original; la diferencia
es que aquí el motivo explica qué hacer para desbloquearlo.
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

#: Prefijos de terminal que se dejan pasar cuando la palanca está en automático.
PREFIJOS_PERMITIDOS = [
    "cd", "ls", "git", "npm", "yarn", "pnpm", "bun", "deno", "node", "make",
    "cargo", "go", "python3", "python", "ruby", "bash", "zsh", "sh", "pytest",
]


class AgenteCursor(AgenteIA):
    id = "cursor"
    nombre = "Cursor"
    url_documentacion = "https://cursor.com/docs"

    eventos = (
        EventoEnganche("sessionStart", "sessionStart", EstadoIA.SESION_INICIADA),
        EventoEnganche("preToolUse", "preToolUse", EstadoIA.HERRAMIENTA_EN_CURSO, 20, permiso=True),
        EventoEnganche("postToolUse", "postToolUse", EstadoIA.HERRAMIENTA_TERMINADA),
        EventoEnganche("stop", "stop", EstadoIA.DETENIDO),
        EventoEnganche("sessionEnd", "sessionEnd", EstadoIA.SESION_FINALIZADA),
    )

    @classmethod
    def ruta_config(cls) -> Path:
        return Path.home() / ".cursor" / "hooks.json"

    @classmethod
    def ruta_permisos(cls) -> Path:
        return Path.home() / ".cursor" / "permissions.json"

    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        if not evento.permiso or veredicto is None:
            return {"ok": True}
        if veredicto.decision is Decision.PERMITIR:
            return {"permission": "allow"}
        return {"permission": "deny", "reason": motivo_legible(veredicto)}

    @classmethod
    def sincronizar_palanca(cls, automatica: bool) -> Optional[str]:
        """Ajusta ``terminalAllowlist`` en ``~/.cursor/permissions.json``.

        Es la lista que consulta el agente del editor; sin ella el terminal
        integrado sigue pidiendo permiso aunque el enganche haya dicho «allow».
        """
        ruta = cls.ruta_permisos()
        datos = leer_json(ruta)
        lista = datos.get("terminalAllowlist")
        lista = [x for x in lista if isinstance(x, str)] if isinstance(lista, list) else []
        propios = set(PREFIJOS_PERMITIDOS)
        if automatica:
            nuevos = [p for p in PREFIJOS_PERMITIDOS if p not in lista]
            if not nuevos:
                return None
            lista.extend(nuevos)
        else:
            if not propios & set(lista):
                return None
            lista = [x for x in lista if x not in propios]
        datos["terminalAllowlist"] = lista
        escribir_json(ruta, datos)
        modo = "ampliada" if automatica else "recortada"
        return f"Lista de terminal {modo} en {ruta}"

    @classmethod
    def instalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        mensajes: list[str] = []
        if copia := respaldar(ruta):
            mensajes.append(f"Copia de seguridad en {copia}")
        datos = leer_json(ruta)
        datos.setdefault("version", 1)
        seccion = datos.setdefault("hooks", {})
        if not isinstance(seccion, dict):
            seccion = {}
            datos["hooks"] = seccion
        fusionar_enganches(seccion, cls.eventos, cls.id)
        escribir_json(ruta, datos)
        mensajes.append(f"{len(cls.eventos)} eventos registrados en {ruta}")
        return mensajes

    @classmethod
    def desinstalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return [f"No hay configuración de Cursor en {ruta}"]
        datos = leer_json(ruta)
        seccion = datos.get("hooks")
        if not isinstance(seccion, dict):
            return ["Cursor no tenía enganches de TecladoIA"]
        quitados = limpiar_enganches(seccion)
        if not seccion:
            datos.pop("hooks", None)
        escribir_json(ruta, datos)
        cls.sincronizar_palanca(False)
        return [f"{quitados} enganches retirados de {ruta}"]
