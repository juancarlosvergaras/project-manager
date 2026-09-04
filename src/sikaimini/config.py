"""Configuración de SikaiMini: dónde vive y qué guarda.

Va en ``%APPDATA%\\SikaiMini\\config.json`` (o en ``$SIKAIMINI_INICIO`` si está
puesta, que es lo que usan las pruebas). Misma trampa que en TecladoIA y
MiniMic: la aplicación de Claude está empaquetada y Windows le redirige
``AppData``; lo que se guarde desde una sesión de Claude no lo ve el servicio
de la tarea programada. Para eso está ``ajustar_config.py --app SikaiMini``.
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

from . import protocolo

NOMBRE = "SikaiMini"

#: Combinación privada de la tecla del micrófono. F15: el AhaKey tiene F13 y
#: el MiniMic F14, y Windows solo deja reservar cada combinación a un proceso.
ATAJO_MICROFONO = "ctrl-mayus-alt-f15"

#: Lo que trae el teclado de fábrica, leído el 4/9/2026: retroceso, Intro,
#: Ctrl+Win (el atajo de Wispr Flow), volumen en la perilla y Alt derecho al pulsarla.
TECLAS_DE_FABRICA = ("retroceso", "intro", "ctrl-win", "vol+", "vol-", "ralt")

#: Lo que se quiere: las dos teclas como venían, la del micrófono con la
#: combinación privada, y la perilla como rueda del ratón con clic central.
TECLAS_DESEADAS = ("retroceso", "intro", ATAJO_MICROFONO, "rueda-abajo", "rueda-arriba", "clic-central")

#: Luces: -1 en el modo significa «no tocar lo que tenga el teclado».
LUCES_SIN_TOCAR = -1


def directorio_base() -> Path:
    propio = os.environ.get("SIKAIMINI_INICIO")
    if propio:
        return Path(propio)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / NOMBRE
    return Path.home() / ".sikaimini"


def ruta_config() -> Path:
    return directorio_base() / "config.json"


def ruta_registro() -> Path:
    return directorio_base() / "servicio.log"


@dataclass
class Ajustes:
    # --- panel ---
    puerto_panel: int = 8772
    host_panel: str = "127.0.0.1"
    clave_panel: str = ""

    # --- a quién se le habla (igual que en MiniMic) ---
    programa: str = "activo"
    alto_cuadro: int = 0
    pinchar_cuadro: bool = True
    enviar_al_cerrar: bool = True
    usar_microfono_propio: bool = True
    atajos_dictado: dict[str, str] = field(default_factory=lambda: dict(ATAJOS_DE_FABRICA))

    # --- el micrófono ---
    adoptar_microfono: bool = True
    modo_microfono: int = protocolo.MICROFONO_PULSAR
    pitido_al_abrir: bool = False

    # --- las teclas y la perilla ---
    #: Lo que se quiere que haga cada pieza (índices 0..5: No, Sí, micrófono,
    #: giro A, giro B, pulsación de la perilla).
    teclas: list[str] = field(default_factory=lambda: list(TECLAS_DESEADAS))
    #: Último mapa leído del teclado, para enseñarlo cuando va por el receptor.
    ultimo_mapa: list[str] = field(default_factory=list)

    # --- el portero del Mac mini ---
    #: A quién se presenta el servicio para que sikaimini.proyectoia.org pase a
    #: este PC. Es la dirección de Tailscale del Mac mini; vacío = no presentarse.
    #: Solo se usa con clave puesta: sin clave, el panel no se publica.
    portero: str = "100.65.52.65:8027"
    usar_portero: bool = True

    # --- las luces ---
    #: Modo que se le graba al conectarlo por cable; -1 = dejar el que tenga.
    luces_modo: int = LUCES_SIN_TOCAR
    luces_color: str = "#ffffff"

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
            if nombre in ("teclas", "ultimo_mapa"):
                if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
                    continue
            if nombre == "atajos_dictado":
                if not isinstance(valor, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in valor.items()):
                    continue
                valor = {**ATAJOS_DE_FABRICA, **{k: v for k, v in valor.items() if k in ATAJOS_DE_FABRICA}}
            limpio[nombre] = valor
        ajustes = cls(**limpio)
        if len(ajustes.teclas) != protocolo.NUMERO_DE_TECLAS:
            ajustes.teclas = list(TECLAS_DESEADAS)
        if ajustes.modo_microfono not in (protocolo.MICROFONO_MANTENER, protocolo.MICROFONO_PULSAR):
            ajustes.modo_microfono = protocolo.MICROFONO_PULSAR
        if not LUCES_SIN_TOCAR <= ajustes.luces_modo <= 255:
            ajustes.luces_modo = LUCES_SIN_TOCAR
        try:
            protocolo.color_desde_texto(ajustes.luces_color)
        except protocolo.ErrorProtocolo:
            ajustes.luces_color = "#ffffff"
        return ajustes

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
