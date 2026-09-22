"""Configuración de OneKey: dónde vive y qué guarda.

Va en ``%APPDATA%\\OneKey\\config.json`` (o en ``$ONEKEY_INICIO`` si está
puesta, que es lo que usan las pruebas). Misma trampa que en los demás: la
aplicación de Claude está empaquetada y Windows le redirige ``AppData``; lo que
se guarde desde una sesión de Claude no lo ve el servicio de la tarea
programada. Para eso está ``ajustar_config.py --app OneKey``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from minimic.config import (  # noqa: F401 - se reexportan: mismos programas, mismo dictado
    ATAJOS_DE_FABRICA, PROGRAMAS, aplicar_atajos_de_dictado, programa_por_proceso,
)

NOMBRE = "OneKey"

#: Nombre Bluetooth con el que se vende el botón.
BOTON_DE_FABRICA = "AI_VOICE"


def directorio_base() -> Path:
    propio = os.environ.get("ONEKEY_INICIO")
    if propio:
        return Path(propio)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / NOMBRE
    return Path.home() / ".onekey"


def ruta_config() -> Path:
    return directorio_base() / "config.json"


def ruta_registro() -> Path:
    return directorio_base() / "servicio.log"


@dataclass
class Ajustes:
    # --- panel ---
    puerto_panel: int = 8774
    host_panel: str = "127.0.0.1"
    clave_panel: str = ""

    # --- el botón ---
    #: Nombre Bluetooth del botón. Se reconoce por el aparato del que viene la
    #: pulsación, no por la tecla que manda. Vacío = no buscar ninguno.
    boton_bluetooth: str = BOTON_DE_FABRICA

    # --- a quién se le habla (igual que en MiniMic) ---
    programa: str = "activo"
    alto_cuadro: int = 0
    pinchar_cuadro: bool = True
    #: Al cerrar el dictado con el botón, mandar Intro: «pulsa y habla, vuelve
    #: a pulsar y el texto entra», que es como el fabricante lo vende.
    enviar_al_cerrar: bool = True
    usar_microfono_propio: bool = True
    atajos_dictado: dict[str, str] = field(default_factory=lambda: dict(ATAJOS_DE_FABRICA))

    # --- el micrófono ---
    adoptar_microfono: bool = True  #: el manos libres del botón como micrófono del sistema
    pitido_al_abrir: bool = False

    # --- el portero del Mac mini ---
    #: A quién se presenta el servicio para que onekey.proyectoia.org pase a
    #: este PC. Es la dirección de Tailscale del Mac mini; vacío = no presentarse.
    portero: str = "100.65.52.65:8033"
    usar_portero: bool = True

    def programa_elegido(self, proceso_al_frente: str = "") -> dict[str, str]:
        if self.programa == "activo":
            return programa_por_proceso(proceso_al_frente)
        for p in PROGRAMAS:
            if p["id"] == self.programa:
                return p
        return PROGRAMAS[-1]

    # --- disco ---
    @classmethod
    def cargar(cls, ruta: Path | None = None) -> "Ajustes":
        ruta = ruta or ruta_config()
        try:
            crudo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(crudo, dict):
            return cls()
        conocidos = {f.name: f for f in fields(cls)}
        limpio: dict[str, Any] = {}
        for nombre, valor in crudo.items():
            if nombre not in conocidos:
                continue
            tipo = conocidos[nombre].type
            if tipo in ("int", int) and (not isinstance(valor, int) or isinstance(valor, bool)):
                continue
            if tipo in ("bool", bool) and not isinstance(valor, bool):
                continue
            if tipo in ("str", str) and not isinstance(valor, str):
                continue
            if nombre == "atajos_dictado":
                if not isinstance(valor, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in valor.items()):
                    continue
                valor = {**ATAJOS_DE_FABRICA, **{k: v for k, v in valor.items() if k in ATAJOS_DE_FABRICA}}
            limpio[nombre] = valor
        return cls(**limpio)

    def guardar(self, ruta: Path | None = None) -> Path:
        ruta = ruta or ruta_config()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(ruta)
        return ruta

    def como_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["clave_panel"] = bool(self.clave_panel)  # nunca se devuelve la clave
        return datos
