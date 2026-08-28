"""Dos pitidos para avisar sin que tengas que estar mirando.

El modo manos libres abre el micrófono cuando la IA termina, y eso solo sirve
si te enteras: si estás leyendo otra cosa, el dictado se abre, se cansa de
esperar y se cierra sin que hayas dicho nada. El aviso tiene que entrar por el
oído, que es el sentido que no estabas usando.

Dos pitidos cortos y no uno: un pitido suelto se confunde con cualquiera de los
cien que da Windows al día. Dos seguidos y agudos no se confunden con nada.

Se puede silenciar —hay quien trabaja con auriculares puestos o gente al lado—
y entonces esto no suena, pero el micrófono se abre igual.
"""

from __future__ import annotations

import os
import sys
import threading

from .registro import obtener

_log = obtener("sonido")

#: Los dos tonos: (frecuencia en hercios, duración en milisegundos). Agudos y
#: cortos para que se distingan de los avisos del sistema, que son graves.
DOS_PITIDOS = ((1180, 90), (1480, 110))

#: Pausa entre uno y otro. Sin ella suenan como un solo pitido largo.
PAUSA_MS = 60


def hay_soporte() -> bool:
    """¿Sabe este equipo dar un pitido por su cuenta?"""
    if os.name != "nt":
        return False
    try:
        import winsound  # noqa: F401
    except ImportError:
        return False
    return True


def _sonar(tonos) -> None:
    try:
        import time

        import winsound

        for indice, (hercios, milisegundos) in enumerate(tonos):
            if indice:
                time.sleep(PAUSA_MS / 1000)
            winsound.Beep(int(hercios), int(milisegundos))
    except Exception:  # noqa: BLE001 - sin altavoz, o el equipo lo prohíbe
        _log.debug("No se pudo dar el aviso sonoro", exc_info=True)


def avisar(tonos=DOS_PITIDOS) -> bool:
    """Da el aviso sin hacer esperar a nadie.

    Suena en un hilo aparte a propósito: ``winsound.Beep`` **bloquea** todo lo
    que dure el tono, y quien llama aquí acaba de abrir el micrófono. Doscientos
    milisegundos de retraso en esa mano son doscientos milisegundos en los que
    lo que digas no se está grabando.
    """
    if not hay_soporte():
        return False
    hilo = threading.Thread(target=_sonar, args=(tonos,), daemon=True)
    hilo.start()
    return True


__all__ = ["avisar", "hay_soporte", "DOS_PITIDOS"]
