"""Mira qué aplicación tienes delante para que el teclado la acompañe.

Hay una asimetría incómoda en todo esto. Los programas de IA de línea de órdenes
—Claude Code, Codex, Cursor, Kimi, Gemini— avisan de lo que hacen a través de sus
enganches, así que el teclado puede reflejar si están pensando o esperándote. Las
aplicaciones de escritorio, como ChatGPT, no avisan de nada: no tienen enganches
ni forma de tenerlos. Si el teclado solo escuchara a los enganches, se quedaría
atado a un único programa y encendido con lo último que pasó, aunque hace rato
que estés en otra cosa.

Esto lo arregla por el otro lado: en vez de esperar a que la aplicación hable, se
mira cuál está delante. Al cambiar de aplicación, el teclado cambia de modo —y
con el modo cambian sus cuatro teclas y su pantalla—. Es menos fino que un
enganche, porque solo sabe *dónde estás* y no *qué está pasando*, pero funciona
con cualquier programa, incluidos los que nunca van a avisar.

Solo tiene sentido en el equipo donde trabajas, así que es cosa de Windows; en
macOS y Linux se queda quieto en vez de fallar.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import re
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable, Optional

from .registro import obtener

_log = obtener("enfoque")

#: Cada cuánto se mira quién está delante. Suficientemente rápido para que se
#: note al cambiar de ventana, suficientemente lento para no molestar a nadie.
INTERVALO_S = 0.7


@dataclass(frozen=True)
class Ventana:
    """La aplicación que tiene el foco ahora mismo."""

    proceso: str
    titulo: str

    def coincide(self, patron: str, en: str = "proceso") -> bool:
        """¿Le pega este patrón?

        Por omisión se compara solo con el **nombre del programa**, y hay motivo:
        el título de una ventana cambia con lo que estés haciendo. Una regla
        «chatgpt» que mirase el título saltaba estando en Claude en cuanto la
        conversación se llamaba algo con «ChatGPT» dentro. Mirar el título sigue
        siendo útil —para distinguir dos pestañas del mismo navegador, por
        ejemplo—, pero hay que pedirlo a propósito.
        """
        patron = (patron or "").strip().lower()
        if not patron:
            return False
        if en == "titulo":
            return patron in self.titulo.lower()
        if en == "cualquiera":
            return patron in self.proceso.lower() or patron in self.titulo.lower()
        return patron in self.proceso.lower()


def hay_soporte() -> bool:
    return os.name == "nt"


def _ventana_al_frente() -> Optional[Ventana]:
    """Nombre de programa y título de la ventana que tiene el foco."""
    if not hay_soporte():
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    largo = user32.GetWindowTextLengthW(hwnd)
    titulo = ""
    if largo:
        memoria = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, memoria, largo + 1)
        titulo = memoria.value

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return Ventana("", titulo)

    # PROCESS_QUERY_LIMITED_INFORMATION: lo mínimo para preguntar el nombre, y
    # lo único que se concede sin privilegios sobre procesos de otro usuario.
    manejador = kernel32.OpenProcess(0x1000, False, pid.value)
    if not manejador:
        return Ventana("", titulo)
    try:
        tamano = wintypes.DWORD(1024)
        memoria = ctypes.create_unicode_buffer(tamano.value)
        if kernel32.QueryFullProcessImageNameW(
            manejador, 0, memoria, ctypes.byref(tamano)
        ):
            proceso = memoria.value.rsplit("\\", 1)[-1]
            proceso = re.sub(r"\.exe$", "", proceso, flags=re.I)
        else:
            proceso = ""
    finally:
        kernel32.CloseHandle(manejador)
    return Ventana(proceso, titulo)


class Vigilante:
    """Avisa cada vez que cambias de aplicación."""

    def __init__(self, al_cambiar: Callable[[Ventana], None]) -> None:
        self.al_cambiar = al_cambiar
        self.actual: Optional[Ventana] = None

    async def correr(self, intervalo_s: float = INTERVALO_S) -> None:
        if not hay_soporte():
            _log.info("Seguir a la aplicación activa solo funciona en Windows.")
            return
        while True:
            try:
                ventana = _ventana_al_frente()
            except Exception:  # noqa: BLE001 - preguntar por una ventana nunca debe tumbar nada
                _log.debug("No se pudo leer la ventana al frente", exc_info=True)
                ventana = None
            # Solo interesa cambiar de programa. El título se mueve solo —al
            # abrir un archivo, al renombrar una conversación— y reaccionar a
            # eso hacía que el teclado se peleara con el modo que pusieras tú.
            cambio = ventana is not None and (
                self.actual is None or ventana.proceso != self.actual.proceso
            )
            if cambio:
                self.actual = ventana
                try:
                    self.al_cambiar(ventana)
                except Exception:  # noqa: BLE001
                    _log.exception("Fallo al reaccionar al cambio de aplicación")
            await asyncio.sleep(intervalo_s)


def modo_para(ventana: Ventana, reglas: list[dict]) -> Optional[int]:
    """Qué modo del teclado le toca a esta ventana. ``None`` si a ninguno.

    Gana la primera regla que coincida, así que el orden de la lista es el orden
    de preferencia: lo más específico, arriba.
    """
    for regla in reglas or []:
        patron = str(regla.get("patron") or "")
        if ventana.coincide(patron, str(regla.get("en") or "proceso")):
            try:
                return int(regla.get("modo"))
            except (TypeError, ValueError):
                continue
    return None


__all__ = ["Vigilante", "Ventana", "hay_soporte", "modo_para", "INTERVALO_S"]
