"""Configuración de MiniMic: dónde vive y qué guarda.

Va en ``%APPDATA%\\MiniMic\\config.json`` (o en ``$MINIMIC_INICIO`` si está
puesta, que es lo que usan las pruebas para no tocar la de verdad). Se carga
con tolerancia: un archivo roto o con campos de más devuelve valores de
fábrica en vez de dejar el servicio sin arrancar.

Ojo con la misma trampa que en TecladoIA: la aplicación de Claude está
empaquetada y Windows le redirige ``AppData``. Lo que se guarde desde una
sesión de Claude no lo ve el servicio de la tarea programada. Para eso está
``ajustar_config.py`` en la raíz del proyecto, que se ejecuta por la tarea.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from . import protocolo

NOMBRE = "MiniMic"

#: Combinación privada que manda la tecla blanca una vez configurada. Es la
#: del AhaKey con F14 en vez de F13: los dos servicios conviven en el mismo
#: PC y Windows solo deja reservar cada combinación a un proceso.
ATAJO_MICROFONO = "ctrl-mayus-alt-f14"

#: Lo que trae el teclado de fábrica, para poder devolverlo a como venía.
TECLAS_DE_FABRICA = ("ctrl-a", "ctrl-v", "retroceso", "intro", "ctrl-win")

#: Programas entre los que elegir a quién se le habla. Mismos valores que en
#: TecladoIA: nombre del proceso y cómo abrirlo si no está.
PROGRAMAS = (
    {"id": "claude", "nombre": "Claude", "proceso": "claude", "lanzar": r"shell:appsFolder\Claude_pzs8sxrjxfjjc!Claude"},
    {"id": "chatgpt", "nombre": "ChatGPT", "proceso": "ChatGPT", "lanzar": r"shell:appsFolder\OpenAI.Codex_2p2nqsd0c76g0!App"},
    {"id": "cursor", "nombre": "Cursor", "proceso": "Cursor", "lanzar": ""},
    {"id": "activo", "nombre": "La ventana que esté activa", "proceso": "", "lanzar": ""},
)


def directorio_base() -> Path:
    propio = os.environ.get("MINIMIC_INICIO")
    if propio:
        return Path(propio)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / NOMBRE
    return Path.home() / ".minimic"


def ruta_config() -> Path:
    return directorio_base() / "config.json"


def ruta_registro() -> Path:
    return directorio_base() / "servicio.log"


@dataclass
class Ajustes:
    # --- panel ---
    puerto_panel: int = 8771
    host_panel: str = "127.0.0.1"
    clave_panel: str = ""

    # --- a quién se le habla ---
    programa: str = "claude"  #: uno de PROGRAMAS, por su id
    alto_cuadro: int = 0  #: píxeles desde abajo hasta el cuadro de escribir; 0 = el 10 %
    pinchar_cuadro: bool = True
    enviar_al_cerrar: bool = True  #: al cerrar el dictado con la tecla, manda Intro
    #: Preferir el botón de dictado del propio programa (Claude, ChatGPT) al
    #: Win+H de Windows, que con este micrófono falla mucho. Igual que en TecladoIA.
    usar_microfono_propio: bool = True

    # --- el micrófono ---
    adoptar_microfono: bool = True  #: ponerlo como micrófono del sistema al aparecer
    modo_microfono: int = protocolo.MICROFONO_PULSAR  #: lo que se le escribe al teclado
    pitido_al_abrir: bool = False

    # --- las teclas ---
    #: Lo que se quiere que haga cada tecla (1..5). La blanca es la 5.
    teclas: list[str] = field(default_factory=lambda: [*TECLAS_DE_FABRICA[:4], ATAJO_MICROFONO])
    #: Último mapa leído del teclado, para enseñarlo cuando va por el receptor.
    ultimo_mapa: list[str] = field(default_factory=list)

    def programa_elegido(self) -> dict[str, str]:
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
            if tipo in ("int", int) and not isinstance(valor, int):
                continue
            if tipo in ("bool", bool) and not isinstance(valor, bool):
                continue
            if tipo in ("str", str) and not isinstance(valor, str):
                continue
            if nombre in ("teclas", "ultimo_mapa"):
                if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
                    continue
            limpio[nombre] = valor
        ajustes = cls(**limpio)
        if len(ajustes.teclas) != protocolo.NUMERO_DE_TECLAS:
            ajustes.teclas = [*TECLAS_DE_FABRICA[:4], ATAJO_MICROFONO]
        if ajustes.modo_microfono not in (protocolo.MICROFONO_MANTENER, protocolo.MICROFONO_PULSAR):
            ajustes.modo_microfono = protocolo.MICROFONO_PULSAR
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
