"""Cliente que ejecutan los programas de IA en cada evento.

Es el proceso que arranca en cada llamada, así que tiene tres obligaciones:
empezar rápido, no imprimir nada que el agente no espere y no colgarse nunca.
Si el servicio no responde, imprime una respuesta neutra y termina con código 0:
el agente sigue su camino normal y la persona decide, que es el comportamiento
seguro.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Any, Optional

from . import agentes
from .agentes.base import AgenteIA, EventoEnganche
from .config import Ajustes, ruta_socket

TIEMPO_ESPERA_S = 6.0


#: Margen para que llegue el JSON del agente antes de seguir sin él.
ESPERA_ENTRADA_S = 0.5


def _hay_entrada() -> bool:
    """¿Hay algo que leer en la entrada estándar?

    Sin esta comprobación, una llamada sin entrada conectada dejaría el proceso
    esperando un fin de fichero que nunca llega, y con él al agente de IA. En
    Windows ``select`` no sirve para ficheros, así que allí basta con descartar
    la terminal interactiva.
    """
    if sys.stdin is None or sys.stdin.closed:
        return False
    try:
        if sys.stdin.isatty():
            return False
    except (OSError, ValueError):
        return False
    if os.name == "nt":
        return True
    try:
        import select

        listos, _, _ = select.select([sys.stdin], [], [], ESPERA_ENTRADA_S)
    except (OSError, ValueError, TypeError):
        return True
    return bool(listos)


def _leer_entrada() -> dict[str, Any]:
    """Lee el JSON que el agente envía por la entrada estándar."""
    if not _hay_entrada():
        return {}
    try:
        crudo = sys.stdin.read()
    except OSError:
        return {}
    if not crudo.strip():
        return {}
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        return {}
    return datos if isinstance(datos, dict) else {}


def extraer_contexto(entrada: dict[str, Any]) -> dict[str, Any]:
    """Saca herramienta, comando, ruta y sesión de lo que envía el agente.

    Cada programa nombra estos campos a su manera; aquí se aceptan todas las
    variantes conocidas para que las reglas funcionen con cualquiera.
    """
    argumentos = entrada.get("tool_input")
    argumentos = argumentos if isinstance(argumentos, dict) else {}

    comando = (
        entrada.get("command")
        or argumentos.get("command")
        or argumentos.get("cmd")
        or argumentos.get("file_path")
        or argumentos.get("path")
    )
    if isinstance(comando, (list, tuple)):
        comando = " ".join(str(p) for p in comando)

    contexto = {
        "herramienta": entrada.get("tool_name") or entrada.get("toolName") or entrada.get("name"),
        "comando": str(comando)[:500] if comando else None,
        "ruta": entrada.get("cwd") or entrada.get("workspace_path"),
        "sesion": entrada.get("session_id") or entrada.get("sessionId"),
    }
    return {c: v for c, v in contexto.items() if v}


def _pedir(peticion: dict[str, Any], ajustes: Ajustes) -> Optional[dict[str, Any]]:
    """Envía la petición al servicio; devuelve ``None`` si no contesta."""
    carga = (json.dumps(peticion, ensure_ascii=False) + "\n").encode("utf-8")
    for familia, direccion in _destinos(ajustes):
        try:
            with socket.socket(familia, socket.SOCK_STREAM) as cliente:
                cliente.settimeout(TIEMPO_ESPERA_S)
                cliente.connect(direccion)
                cliente.sendall(carga)
                respuesta = _leer_linea(cliente)
        except (OSError, socket.timeout):
            continue
        if respuesta is None:
            continue
        try:
            datos = json.loads(respuesta)
        except json.JSONDecodeError:
            continue
        if isinstance(datos, dict):
            return datos
    return None


def _destinos(ajustes: Ajustes) -> list[tuple[int, Any]]:
    destinos: list[tuple[int, Any]] = []
    if os.name != "nt" and hasattr(socket, "AF_UNIX"):
        destinos.append((socket.AF_UNIX, str(ruta_socket())))
    for desplazamiento in range(3):
        destinos.append((socket.AF_INET, ("127.0.0.1", ajustes.puerto_hooks + desplazamiento)))
    return destinos


def _leer_linea(cliente: socket.socket) -> Optional[str]:
    trozos: list[bytes] = []
    while True:
        try:
            trozo = cliente.recv(4096)
        except (OSError, socket.timeout):
            return None
        if not trozo:
            break
        trozos.append(trozo)
        if b"\n" in trozo:
            break
    if not trozos:
        return None
    return b"".join(trozos).decode("utf-8", "replace").strip()


def ejecutar(
    agente_id: str,
    evento_nombre: str,
    contexto_extra: Optional[dict[str, Any]] = None,
    ajustes: Optional[Ajustes] = None,
) -> int:
    """Punto de entrada de ``tecladoia enganche``. Devuelve el código de salida."""
    ajustes = ajustes or Ajustes.cargar()
    agente: Optional[type[AgenteIA]] = agentes.obtener(agente_id)
    if agente is None:
        print(json.dumps({"error": f"Agente desconocido: {agente_id}"}, ensure_ascii=False))
        return 2
    evento: Optional[EventoEnganche] = agente.evento(evento_nombre)
    if evento is None:
        print(json.dumps({"error": f"Evento desconocido: {evento_nombre}"}, ensure_ascii=False))
        return 2

    contexto = extraer_contexto(_leer_entrada())
    contexto.update({c: v for c, v in (contexto_extra or {}).items() if v})

    respuesta = _pedir(
        {
            "orden": "evento",
            "agente": agente.id,
            "evento": evento.interno,
            "contexto": contexto,
        },
        ajustes,
    )

    if respuesta is None:
        # Sin servicio no hay palanca que valga: se contesta lo mínimo para no
        # estorbar y la decisión queda en manos de la persona.
        if evento.permiso:
            print(
                "[tecladoia] El servicio no responde; decide tú. "
                "Arráncalo con «tecladoia servicio».",
                file=sys.stderr,
            )
        print(json.dumps(agente.respuesta(evento, None), ensure_ascii=False))
        return 0

    salida = respuesta.get("respuesta")
    print(json.dumps(salida if isinstance(salida, dict) else {}, ensure_ascii=False))

    if evento.permiso and respuesta.get("decision") != "permitir":
        print(
            f"[tecladoia] {respuesta.get('explicacion') or 'Decisión devuelta a la persona.'}",
            file=sys.stderr,
        )
    return 0
