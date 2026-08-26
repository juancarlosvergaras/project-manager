"""Adaptador de Codex CLI.

Codex lee su política de aprobación al empezar la sesión, así que responder al
enganche no basta: hay que alinear ``approval_policy`` en ``~/.codex/config.toml``.
Automático es ``never`` (no pregunta) y manual es ``untrusted`` (pregunta salvo
en las órdenes de solo lectura que Codex considera seguras).
"""

from __future__ import annotations

import re
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

_PATRON_POLITICA = re.compile(r"^\s*approval_policy\s*=", re.MULTILINE)


class AgenteCodex(AgenteIA):
    id = "codex"
    nombre = "Codex CLI"
    url_documentacion = "https://developers.openai.com/codex/config-reference"

    eventos = (
        EventoEnganche("CodexSessionStart", "SessionStart", EstadoIA.SESION_INICIADA, filtro="startup|resume|clear"),
        EventoEnganche("CodexUserPromptSubmit", "UserPromptSubmit", EstadoIA.PETICION_ENVIADA),
        EventoEnganche("CodexPreToolUse", "PreToolUse", EstadoIA.HERRAMIENTA_EN_CURSO, 20, filtro="*"),
        EventoEnganche(
            "CodexPermissionRequest",
            "PermissionRequest",
            EstadoIA.ESPERANDO_APROBACION,
            20,
            permiso=True,
            filtro="*",
        ),
        EventoEnganche("CodexPostToolUse", "PostToolUse", EstadoIA.HERRAMIENTA_TERMINADA, filtro="*"),
        EventoEnganche("CodexStop", "Stop", EstadoIA.DETENIDO),
    )

    @classmethod
    def ruta_config(cls) -> Path:
        return Path.home() / ".codex" / "hooks.json"

    @classmethod
    def ruta_toml(cls) -> Path:
        return Path.home() / ".codex" / "config.toml"

    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        if not evento.permiso or veredicto is None:
            # Codex valida el esquema de los eventos de ciclo de vida: {} exacto.
            return {}
        salida: dict[str, Any] = {"hookEventName": "PermissionRequest"}
        if veredicto.decision is Decision.PERMITIR:
            salida["decision"] = {"behavior": "allow"}
        elif veredicto.decision is Decision.DENEGAR:
            salida["decision"] = {"behavior": "deny", "message": motivo_legible(veredicto)}
        # Si hay que preguntar no se dice nada: Codex enseña su propio aviso.
        return {"hookSpecificOutput": salida}

    @classmethod
    def sincronizar_palanca(cls, automatica: bool) -> Optional[str]:
        ruta = cls.ruta_toml()
        if not ruta.exists():
            return None
        deseada = "never" if automatica else "untrusted"
        linea = f'approval_policy = "{deseada}"'
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            return None

        lineas = texto.splitlines()
        # ``approval_policy`` es una clave de nivel superior: tiene que quedar
        # por encima de la primera sección [tabla].
        primera_seccion = next(
            (i for i, l in enumerate(lineas) if l.strip().startswith("[")), len(lineas)
        )
        for indice in range(primera_seccion):
            if _PATRON_POLITICA.match(lineas[indice]):
                if lineas[indice].strip() == linea:
                    return None
                lineas[indice] = linea
                break
        else:
            lineas.insert(primera_seccion, linea)

        try:
            ruta.write_text("\n".join(lineas).rstrip() + "\n", encoding="utf-8")
        except OSError:
            return None
        return f"approval_policy = «{deseada}» en {ruta}"

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
        fusionar_enganches(seccion, cls.eventos, cls.id)
        escribir_json(ruta, datos)
        mensajes.append(f"{len(cls.eventos)} eventos registrados en {ruta}")
        mensajes.append(cls._activar_funcion_hooks())
        return [m for m in mensajes if m]

    @classmethod
    def _activar_funcion_hooks(cls) -> str:
        """Codex necesita ``[features] hooks = true`` para leer hooks.json."""
        ruta = cls.ruta_toml()
        texto = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
        if re.search(r"^\s*hooks\s*=\s*true", texto, re.MULTILINE):
            return f"«hooks» ya estaba activado en {ruta}"
        respaldar(ruta)
        if "[features]" in texto:
            texto = texto.replace("[features]", "[features]\nhooks = true", 1)
        else:
            texto = texto.rstrip() + "\n\n[features]\nhooks = true\n"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto.lstrip("\n"), encoding="utf-8")
        return f"«[features] hooks = true» añadido en {ruta}"

    @classmethod
    def desinstalar(cls) -> list[str]:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return [f"No hay configuración de Codex en {ruta}"]
        datos = leer_json(ruta)
        seccion = datos.get("hooks")
        if not isinstance(seccion, dict):
            return ["Codex no tenía enganches de TecladoIA"]
        quitados = limpiar_enganches(seccion)
        if not seccion:
            datos.pop("hooks", None)
        escribir_json(ruta, datos)
        return [
            f"{quitados} enganches retirados de {ruta}",
            "Revisa «approval_policy» en ~/.codex/config.toml si quieres restaurarla a mano.",
        ]
