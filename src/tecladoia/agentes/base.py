"""Pieza común de los adaptadores de agentes de IA.

Un adaptador traduce entre dos mundos: los eventos que emite un programa de IA
(Claude Code, Codex, Cursor, Kimi, Gemini CLI…) y el modelo interno de
:mod:`tecladoia.modelo`. Cada uno declara qué eventos escucha, cómo se instala
en su fichero de configuración y qué JSON espera recibir de vuelta.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from ..modelo import Decision, EstadoIA, Veredicto

MARCA = "tecladoia"
MARCA_INICIO = "# INICIO TecladoIA"
MARCA_FIN = "# FIN TecladoIA"


@dataclass(frozen=True)
class EventoEnganche:
    """Un evento del agente que queremos interceptar."""

    interno: str
    """Nombre que se le pasa a ``tecladoia enganche`` (único entre agentes)."""

    externo: str
    """Nombre del evento tal y como lo llama el programa de IA."""

    estado: EstadoIA
    """Estado que se refleja en la barra LED."""

    tiempo_limite: int = 10
    """Segundos que el agente espera por nuestra respuesta."""

    permiso: bool = False
    """Si es cierto, este evento decide si la acción sigue adelante."""

    filtro: Optional[str] = None
    """Patrón ``matcher`` con el que el agente filtra herramientas."""


class AgenteIA:
    """Adaptador de un programa de IA."""

    id: str = ""
    nombre: str = ""
    url_documentacion: str = ""
    eventos: tuple[EventoEnganche, ...] = ()

    # --- consulta -------------------------------------------------------
    @classmethod
    def evento(cls, interno: str) -> Optional[EventoEnganche]:
        for evento in cls.eventos:
            if evento.interno == interno:
                return evento
        return None

    @classmethod
    def ruta_config(cls) -> Path:
        raise NotImplementedError

    @classmethod
    def instalado(cls) -> bool:
        ruta = cls.ruta_config()
        if not ruta.exists():
            return False
        try:
            return MARCA in ruta.read_text(encoding="utf-8")
        except OSError:
            return False

    # --- respuesta a un evento -----------------------------------------
    @classmethod
    def respuesta(cls, evento: EventoEnganche, veredicto: Optional[Veredicto]) -> dict[str, Any]:
        """JSON que se imprime por la salida estándar para el agente."""
        return {}

    @classmethod
    def sincronizar_palanca(cls, automatica: bool) -> Optional[str]:
        """Alinea la configuración propia del agente con la palanca.

        Algunos programas leen su política de aprobación una sola vez al
        arrancar la sesión; para ellos no basta con contestar al enganche.
        Devuelve un texto describiendo el cambio, o ``None`` si no hizo falta.
        """
        return None

    # --- instalación ----------------------------------------------------
    @classmethod
    def instalar(cls) -> list[str]:
        raise NotImplementedError

    @classmethod
    def desinstalar(cls) -> list[str]:
        raise NotImplementedError


# --- utilidades compartidas ---------------------------------------------------

def orden_enganche(agente: str, evento: str) -> str:
    """Comando que el agente ejecutará en cada evento.

    Se invoca el intérprete de Python actual en lugar del ejecutable
    ``tecladoia`` porque no siempre está en el ``PATH`` de la terminal donde
    corre el agente (entornos virtuales, Windows, terminales integradas).
    """
    ejecutable = os.environ.get("TECLADOIA_PYTHON") or sys.executable or "python3"
    return f'"{ejecutable}" -m tecladoia enganche {agente} {evento}'


def es_orden_nuestra(orden: Any) -> bool:
    return isinstance(orden, str) and "-m tecladoia enganche" in orden


def leer_json(ruta: Path) -> dict[str, Any]:
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporal.replace(ruta)


def respaldar(ruta: Path) -> Optional[Path]:
    """Guarda una copia con marca de tiempo antes de tocar un fichero ajeno."""
    if not ruta.exists():
        return None
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = ruta.with_name(f"{ruta.name}.{marca}.respaldo")
    try:
        shutil.copy2(ruta, destino)
    except OSError:
        return None
    return destino


def fusionar_enganches(
    seccion: dict[str, Any],
    eventos: Iterable[EventoEnganche],
    agente: str,
    clave_tipo: str = "command",
    tiempo_en_ms: bool = False,
) -> int:
    """Añade nuestros enganches sin borrar los que ya hubiera.

    El proyecto original sobrescribía el bloque ``hooks`` entero, de modo que
    instalar el teclado hacía desaparecer los enganches que la persona ya
    tuviera configurados. Aquí se respetan: se añade una entrada propia,
    reconocible, y al desinstalar se quita solo esa.
    """
    añadidos = 0
    for evento in eventos:
        entrada: dict[str, Any] = {"type": clave_tipo, "command": orden_enganche(agente, evento.interno)}
        entrada["timeout"] = evento.tiempo_limite * 1000 if tiempo_en_ms else evento.tiempo_limite
        entrada["name"] = "TecladoIA"

        grupos = seccion.setdefault(evento.externo, [])
        if not isinstance(grupos, list):
            grupos = []
            seccion[evento.externo] = grupos

        grupo_nuestro = None
        for grupo in grupos:
            if isinstance(grupo, dict) and any(
                es_orden_nuestra(h.get("command")) for h in grupo.get("hooks", []) if isinstance(h, dict)
            ):
                grupo_nuestro = grupo
                break

        if grupo_nuestro is None:
            grupo_nuestro = {"hooks": []}
            if evento.filtro:
                grupo_nuestro["matcher"] = evento.filtro
            grupos.append(grupo_nuestro)
            añadidos += 1
        grupo_nuestro["hooks"] = [entrada]
        if evento.filtro:
            grupo_nuestro["matcher"] = evento.filtro
    return añadidos


def limpiar_enganches(seccion: dict[str, Any]) -> int:
    """Quita únicamente nuestras entradas y devuelve cuántas se quitaron."""
    quitados = 0
    for evento, grupos in list(seccion.items()):
        if not isinstance(grupos, list):
            continue
        restantes = []
        for grupo in grupos:
            if not isinstance(grupo, dict):
                restantes.append(grupo)
                continue
            enganches = [
                h
                for h in grupo.get("hooks", [])
                if not (isinstance(h, dict) and es_orden_nuestra(h.get("command")))
            ]
            if len(enganches) != len(grupo.get("hooks", [])):
                quitados += 1
            if enganches:
                grupo["hooks"] = enganches
                restantes.append(grupo)
        if restantes:
            seccion[evento] = restantes
        else:
            del seccion[evento]
    return quitados


def bloque_marcado(cuerpo: str) -> str:
    return f"{MARCA_INICIO}\n{cuerpo.rstrip()}\n{MARCA_FIN}\n"


def quitar_bloque_marcado(texto: str) -> str:
    """Elimina el bloque delimitado por nuestras marcas, si existe."""
    inicio = texto.find(MARCA_INICIO)
    if inicio < 0:
        return texto
    fin = texto.find(MARCA_FIN, inicio)
    if fin < 0:
        return texto[:inicio].rstrip() + "\n"
    return (texto[:inicio].rstrip() + "\n" + texto[fin + len(MARCA_FIN) :].lstrip("\n")).rstrip() + "\n"


def motivo_legible(veredicto: Optional[Veredicto]) -> str:
    """Texto en español que se le muestra a la persona o al agente."""
    if veredicto is None:
        return "TecladoIA no pudo decidir; la petición sigue el camino normal."
    if veredicto.decision is Decision.DENEGAR:
        return f"Bloqueado por TecladoIA. {veredicto.explicacion}"
    if veredicto.decision is Decision.PREGUNTAR:
        return f"TecladoIA devuelve la decisión a la persona. {veredicto.explicacion}"
    return f"Aprobado por TecladoIA. {veredicto.explicacion}"
