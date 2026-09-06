"""Abrir aplicaciones de Windows desde una tecla.

El teclado solo sabe mandar teclas, así que «abrir Excel» se hace igual que
el dictado: la tecla manda una combinación privada y el servicio, que la
tiene reservada, abre la aplicación. Hay once huecos, ``Ctrl+Mayús+Alt+F1``
a ``F11`` (F12 es la del dictado; F13-F24 no llegan por Bluetooth), y cada
hueco guarda a qué aplicación abre.

La lista de aplicaciones sale de ``Get-StartApps`` (lo mismo que enseña el
menú Inicio: tienda y escritorio, con su ``AppID``) y se abre con
``explorer.exe shell:appsFolder\\<AppID>``, que vale para las dos clases. Si
la aplicación ya está abierta, Windows la trae al frente.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable

registro = logging.getLogger("botonera.lanzador")

HUECOS = tuple(range(1, 12))  #: F1..F11
VK_F1 = 0x70
IDENTIFICADOR_BASE = 0xA1E0
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
_CACHE_S = 120.0
_cache: dict[str, Any] = {"cuando": 0.0, "lista": []}


def accion_del_hueco(hueco: int) -> str:
    if hueco not in HUECOS:
        raise ValueError(f"hueco {hueco}: hay del 1 al 11")
    return f"ctrl-mayus-alt-f{hueco}"


def hueco_de_accion(texto: str) -> int | None:
    """``ctrl-mayus-alt-f3`` → 3; cualquier otra cosa → None."""
    partes = (texto or "").strip().lower().split("-")
    if len(partes) != 4 or sorted(partes[:3]) != ["alt", "ctrl", "mayus"] or not partes[3].startswith("f"):
        return None
    try:
        n = int(partes[3][1:])
    except ValueError:
        return None
    return n if n in HUECOS else None


def hay_soporte() -> bool:
    return os.name == "nt"


def listar_aplicaciones(forzar: bool = False) -> list[dict[str, str]]:
    """Las aplicaciones del menú Inicio: [{nombre, destino}], ordenadas por nombre."""
    if not hay_soporte():
        return []
    if not forzar and _cache["lista"] and time.monotonic() - _cache["cuando"] < _CACHE_S:
        return list(_cache["lista"])
    try:
        hecho = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
            capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        crudo = json.loads(hecho.stdout.decode("utf-8", "replace") or "[]")
    except Exception as e:  # noqa: BLE001
        registro.warning("no se pudo listar las aplicaciones: %s", e)
        return list(_cache["lista"])
    if isinstance(crudo, dict):
        crudo = [crudo]
    lista = sorted(
        ({"nombre": str(a.get("Name", "")).strip(), "destino": str(a.get("AppID", ""))} for a in crudo if isinstance(a, dict) and a.get("AppID")),
        key=lambda a: a["nombre"].casefold(),
    )
    _cache["lista"], _cache["cuando"] = lista, time.monotonic()
    return list(lista)


def abrir(destino: str) -> None:
    """Abre la aplicación: un AppID del menú Inicio, un ``shell:…`` o una ruta."""
    destino = (destino or "").strip()
    if not destino:
        raise ValueError("no hay aplicación que abrir")
    if not hay_soporte():
        raise RuntimeError("abrir aplicaciones es cosa de Windows")
    if os.path.exists(destino):
        os.startfile(destino)  # type: ignore[attr-defined]
        return
    objetivo = destino if destino.lower().startswith("shell:") else "shell:appsFolder\\" + destino
    subprocess.Popen(["explorer.exe", objetivo], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class EscuchaAtajos:
    """Reserva Ctrl+Mayús+Alt+F1..F11 y avisa con el número de hueco. Va en su propio hilo."""

    def __init__(self, al_pulsar: Callable[[int], None]) -> None:
        self.al_pulsar = al_pulsar
        self.reservados: list[int] = []
        self._parar = False
        self._hilo: int | None = None

    def correr(self) -> None:
        if not hay_soporte():
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        self._hilo = kernel32.GetCurrentThreadId()
        modificadores = MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT
        for intento in range(20):
            for hueco in HUECOS:
                if hueco in self.reservados:
                    continue
                if user32.RegisterHotKey(None, IDENTIFICADOR_BASE + hueco, modificadores, VK_F1 + hueco - 1):
                    self.reservados.append(hueco)
            if len(self.reservados) == len(HUECOS):
                break
            time.sleep(0.5)
        faltan = [h for h in HUECOS if h not in self.reservados]
        if faltan:
            registro.error("no se pudieron reservar las combinaciones de los huecos %s (¿otra copia del servicio?)", faltan)
        else:
            registro.info("Escuchando las teclas de aplicaciones (ctrl+alt+may+f1..f11)")
        try:
            from ctypes import wintypes
            mensaje = wintypes.MSG()
            while not self._parar:
                if user32.GetMessageW(ctypes.byref(mensaje), None, 0, 0) <= 0:
                    break
                if mensaje.message == WM_HOTKEY and IDENTIFICADOR_BASE < mensaje.wParam <= IDENTIFICADOR_BASE + len(HUECOS):
                    hueco = int(mensaje.wParam) - IDENTIFICADOR_BASE
                    try:
                        self.al_pulsar(hueco)
                    except Exception:  # noqa: BLE001 - un fallo no debe callar las demás teclas
                        registro.exception("fallo al atender la tecla de aplicación %d", hueco)
        finally:
            for hueco in self.reservados:
                user32.UnregisterHotKey(None, IDENTIFICADOR_BASE + hueco)
            self.reservados = []

    def parar(self) -> None:
        self._parar = True
        if hay_soporte() and self._hilo:
            try:
                ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW(self._hilo, WM_QUIT, 0, 0)
            except Exception:  # noqa: BLE001
                pass


def hilo_de_escucha(al_pulsar: Callable[[int], None]) -> tuple[EscuchaAtajos, threading.Thread]:
    escucha = EscuchaAtajos(al_pulsar)
    hilo = threading.Thread(target=escucha.correr, name="botonera-aplicaciones", daemon=True)
    hilo.start()
    return escucha, hilo
