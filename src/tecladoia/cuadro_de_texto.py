"""Encuentra el cuadro de escribir de un programa y le da el foco.

El dictado de Windows escribe donde esté el cursor de texto, así que traer la
ventana al frente no basta: si el cuadro no tiene el foco, Windows contesta
«selecciona un cuadro de texto y vuelve a intentarlo» y no dicta nada.

Adivinar dónde está el cuadro no funciona. Se probó y falla por dos motivos: el
escalado de pantalla mueve las coordenadas, y el cuadro **se mueve solo** —en
ChatGPT, con la conversación vacía está a media altura, y baja cuando hay
mensajes—. Cualquier proporción fija acierta en un caso y falla en el otro.

Así que se le pregunta a Windows. Su capa de accesibilidad sabe exactamente
dónde está cada campo de texto y permite darle el foco sin tocar el ratón. Con
una particularidad que cuesta descubrir: **Chromium no publica ese árbol hasta
que alguien se lo pide**. Aplicaciones como ChatGPT o Claude —que son Chromium
por dentro— responden «no tengo ningún campo» a la primera pregunta y enseñan
todos sus campos a la segunda, después de despertarlas con un ``WM_GETOBJECT``.

Si la biblioteca no está disponible, se avisa y quien llama decide qué hacer.
"""

from __future__ import annotations

import ctypes
import os
import time
from typing import Optional

from .registro import obtener

_log = obtener("cuadro")

#: Tipos de control que se consideran «un sitio donde escribir».
TIPO_EDIT = 50004
TIPO_DOCUMENT = 50030

#: Mensaje con el que se despierta el árbol de accesibilidad de Chromium.
_WM_GETOBJECT = 0x003D
_OBJETOS = (0xFFFFFFFC, 0x00000000)  # raíz de UIA y cliente


def hay_soporte() -> bool:
    """¿Se puede preguntar a la capa de accesibilidad de Windows?"""
    if os.name != "nt":
        return False
    try:
        import comtypes.client  # noqa: F401
    except ImportError:
        return False
    return True


def _automatizacion():
    import comtypes.client as cc

    cc.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA

    return cc.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation), UIA


def _despertar_accesibilidad(hwnd) -> None:
    """Pide el árbol de accesibilidad para que Chromium se digne a publicarlo."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    for objeto in _OBJETOS:
        user32.SendMessageTimeoutW(
            hwnd, _WM_GETOBJECT, 0, ctypes.c_longlong(objeto), 2, 800, None
        )


def _es_el_cuadro(elemento, ancho_ventana: int, alto_ventana: int) -> bool:
    """Descarta lo que no es un cuadro de escribir de verdad.

    El propio documento de la página aparece como campo editable y ocupa la
    ventana entera; darle el foco a eso no sirve de nada.
    """
    if not elemento.CurrentIsKeyboardFocusable:
        return False
    r = elemento.CurrentBoundingRectangle
    ancho, alto = r.right - r.left, r.bottom - r.top
    if ancho <= 0 or alto <= 0:
        return False
    if ancho > ancho_ventana * 0.95 and alto > alto_ventana * 0.8:
        return False  # es el documento entero, no el cuadro
    return True


#: Nombres de cuadro que son una terminal, no el chat. Con la terminal de
#: Claude abierta, su «Terminal input» queda **debajo** del «Prompt» del chat,
#: y la regla de «el más bajo» dictaba en la terminal. Se vio con el MiniMic
#: el 2 de septiembre de 2026: el AhaKey dictaba bien a las 21:53 y a las
#: 22:32 el mismo código elegía la terminal. No era el teclado, era la ventana.
_NO_ES_EL_CHAT = ("terminal", "consola", "console", "search", "buscar", "find")

#: Nombres que son el chat sin duda; ganan a cualquier otro.
_ES_EL_CHAT = ("prompt", "mensaje", "message", "chat", "pregunta", "ask")


def _peso(nombre: str) -> int:
    nombre = (nombre or "").lower()
    if any(palabra in nombre for palabra in _ES_EL_CHAT):
        return 2
    if any(palabra in nombre for palabra in _NO_ES_EL_CHAT):
        return 0
    return 1


def elegir_cuadro(candidatos):
    """Entre varios cuadros, el del chat: por nombre primero y por altura después.

    Sin nombre que ayude, gana el de más abajo, que en un programa de
    conversación es donde se escribe.
    """
    return max(
        candidatos,
        key=lambda e: (_peso(e.CurrentName), e.CurrentBoundingRectangle.bottom),
    )


def enfocar_cuadro(hwnd, intentos: int = 3) -> Optional[dict]:
    """Da el foco al cuadro de escribir de esa ventana.

    Devuelve sus datos si lo encontró, o ``None``. Entre varios candidatos gana
    el que esté más abajo: en un programa de conversación, el sitio donde se
    escribe está debajo de todo lo demás.
    """
    if not hay_soporte():
        return None
    try:
        uia, UIA = _automatizacion()
    except Exception:  # noqa: BLE001 - sin la biblioteca no hay nada que hacer
        _log.debug("No se pudo abrir la automatización de interfaz", exc_info=True)
        return None

    _despertar_accesibilidad(hwnd)
    condicion = uia.CreateOrCondition(
        uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, TIPO_EDIT),
        uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, TIPO_DOCUMENT),
    )

    for intento in range(intentos):
        try:
            raiz = uia.ElementFromHandle(hwnd)
            marco = raiz.CurrentBoundingRectangle
            ancho = marco.right - marco.left
            alto = marco.bottom - marco.top
            hallados = raiz.FindAll(UIA.TreeScope_Descendants, condicion)
        except Exception:  # noqa: BLE001 - la ventana puede irse mientras se mira
            _log.debug("Fallo consultando la ventana", exc_info=True)
            return None

        candidatos = []
        for i in range(hallados.Length):
            elemento = hallados.GetElement(i)
            try:
                if _es_el_cuadro(elemento, ancho, alto):
                    candidatos.append(elemento)
            except Exception:  # noqa: BLE001
                continue

        if candidatos:
            elegido = elegir_cuadro(candidatos)
            r = elegido.CurrentBoundingRectangle
            try:
                elegido.SetFocus()
            except Exception:  # noqa: BLE001 - algunos no dejan; se dirá que no
                _log.debug("El cuadro no aceptó el foco", exc_info=True)
                return None
            nombre = elegido.CurrentName or ""
            _log.info("Cursor puesto en «%s»", nombre or "el cuadro de escribir")
            return {
                "nombre": nombre,
                "izquierda": r.left, "arriba": r.top,
                "derecha": r.right, "abajo": r.bottom,
            }

        # Chromium contesta «no tengo campos» la primera vez y los publica
        # después: se le da tiempo y se vuelve a preguntar.
        if intento < intentos - 1:
            _despertar_accesibilidad(hwnd)
            time.sleep(0.6)

    _log.info("No se encontró ningún cuadro de escribir en esa ventana")
    return None


__all__ = ["enfocar_cuadro", "hay_soporte"]
