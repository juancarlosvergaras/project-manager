"""Usar el micrófono de la propia aplicación en vez del dictado de Windows.

Claude y ChatGPT traen su dictado dentro, y es mejor que el de Windows por una
razón que no es de calidad sino de mecánica: **su botón dice si está grabando**.

Win+H es un interruptor a ciegas. El panel de dictado de Windows no es una
ventana ni se asoma a la capa de accesibilidad —se buscó y no está—, así que no
hay forma de saber en qué posición está. De ahí venían todos los males del
micrófono: pulsabas para cerrar y se abría, Windows lo cerraba solo tras un
silencio y nuestras cuentas se desalineaban, y la primera pulsación tras
reiniciar hacía lo contrario de lo que querías.

El botón de la aplicación, en cambio, expone el patrón ``Toggle`` de la capa de
accesibilidad. Se le puede preguntar **y** pulsar. No hay que adivinar nada.

Lo que se pierde: esto solo vale para programas que tengan dictado propio y lo
publiquen. Para los demás sigue estando Win+H, que funciona en cualquier sitio.
Por eso esto no sustituye al otro, se antepone.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .cuadro_de_texto import _automatizacion, _despertar_accesibilidad, hay_soporte
from .registro import obtener

_log = obtener("microfono")

#: Cómo se llama el botón del micrófono en cada programa.
#:
#: Se buscan trozos, en minúsculas, y basta con que uno encaje. Van varios
#: idiomas porque la aplicación se pone en el del sistema y no controlamos eso:
#: el mismo botón es «Mantén presionado para grabar» o «Hold to record».
NOMBRES_DEL_BOTON = {
    "claude": ("grabar", "record", "dictad", "dictat", "voz", "voice"),
    "chatgpt": ("dictar", "dictate", "voz", "voice", "micr", "grabar"),
}

#: Para lo que no esté en la lista, se prueba con lo más común.
NOMBRES_POR_OMISION = ("dictar", "grabar", "record", "dictat", "micr", "voz", "voice")

#: Identificador del patrón Toggle en la capa de accesibilidad de Windows.
PATRON_TOGGLE = 10015

#: Lo que tarda el botón en reflejar el cambio. Preguntarle antes de esto
#: devuelve el estado viejo — comprobado: tras pulsarlo seguía diciendo
#: «grabando» hasta pasado un momento, y eso hacía creer que no había obedecido.
ESPERA_DEL_ESTADO_S = 1.2


def _trozos_para(programa: str) -> tuple[str, ...]:
    bajo = (programa or "").lower()
    for clave, nombres in NOMBRES_DEL_BOTON.items():
        if clave in bajo:
            return nombres
    return NOMBRES_POR_OMISION


def buscar_boton(hwnd: int, programa: str = "") -> Optional[Any]:
    """El botón de micrófono de esa ventana, si lo publica.

    Devuelve ``None`` sin quejarse cuando no lo hay: no todos los programas
    tienen dictado propio, y quien llama ya sabe qué hacer entonces.
    """
    if not hay_soporte():
        return None
    try:
        uia, UIA = _automatizacion()
    except Exception:  # noqa: BLE001 - sin la biblioteca no hay nada que hacer
        _log.debug("No se pudo abrir la automatización de interfaz", exc_info=True)
        return None

    _despertar_accesibilidad(hwnd)
    trozos = _trozos_para(programa)
    try:
        raiz = uia.ElementFromHandle(hwnd)
        condicion = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50000)
        hallados = raiz.FindAll(UIA.TreeScope_Descendants, condicion)
    except Exception:  # noqa: BLE001 - la ventana puede irse mientras se mira
        _log.debug("Fallo mirando los botones de la ventana", exc_info=True)
        return None

    for i in range(hallados.Length):
        try:
            elemento = hallados.GetElement(i)
            nombre = (elemento.CurrentName or "").strip().lower()
            if not nombre or not any(t in nombre for t in trozos):
                continue
            # Tiene que poder encenderse y apagarse. Un botón que solo se
            # pulsa no sirve: sin saber en qué estado está volveríamos al
            # problema de Win+H, que es justo lo que se viene a resolver.
            #
            # Y no basta con mirar si ``GetCurrentPattern`` devuelve algo:
            # cuando el elemento no admite el patrón devuelve un **puntero
            # nulo**, que en Python no es ``None`` y pasa cualquier
            # comprobación ingenua. El fallo aparece después, al usarlo, con un
            # «NULL COM pointer access» que no dice de dónde viene. Se pide el
            # interruptor de verdad: si sale, sirve.
            if _interruptor(elemento) is None:
                continue
            return elemento
        except Exception:  # noqa: BLE001
            continue
    return None


def _interruptor(boton: Any):
    """El interruptor del botón, o ``None`` si ese botón no tiene."""
    try:
        _, UIA = _automatizacion()
        crudo = boton.GetCurrentPattern(PATRON_TOGGLE)
        if not crudo:  # puntero nulo: el elemento no admite el patrón
            return None
        return crudo.QueryInterface(UIA.IUIAutomationTogglePattern)
    except Exception:  # noqa: BLE001 - el elemento puede irse mientras se mira
        return None


def esta_grabando(boton: Any) -> Optional[bool]:
    """¿Está grabando ahora mismo? ``None`` si no se puede saber."""
    interruptor = _interruptor(boton)
    if interruptor is None:
        return None
    try:
        return bool(interruptor.CurrentToggleState == 1)
    except Exception:  # noqa: BLE001
        return None


def alternar(boton: Any) -> Optional[bool]:
    """Pulsa el botón y devuelve si quedó grabando.

    Se espera antes de leer el estado: el botón tarda un momento en reflejar
    el cambio y preguntarle enseguida devuelve el valor viejo.
    """
    interruptor = _interruptor(boton)
    if interruptor is None:
        return None
    try:
        interruptor.Toggle()
    except Exception:  # noqa: BLE001 - el botón puede irse mientras se pulsa
        _log.debug("El botón del micrófono no aceptó la pulsación", exc_info=True)
        return None
    time.sleep(ESPERA_DEL_ESTADO_S)
    return esta_grabando(boton)


def poner(boton: Any, grabando: bool) -> Optional[bool]:
    """Deja el micrófono como se pida, mirando antes cómo está.

    Aquí está la diferencia con Win+H: como se puede preguntar, se puede
    **poner** en una posición en vez de alternar a ciegas. Si ya estaba como
    se quería, no se toca —y eso evita cerrarle el micrófono a quien está
    hablando, que es lo que hacía el interruptor ciego.
    """
    actual = esta_grabando(boton)
    if actual is None:
        return None
    if actual == grabando:
        return actual
    return alternar(boton)


__all__ = ["buscar_boton", "esta_grabando", "alternar", "poner", "NOMBRES_DEL_BOTON"]
