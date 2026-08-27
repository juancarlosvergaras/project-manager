"""Adaptador de la aplicación de ChatGPT para Windows.

Este agente es distinto a todos los demás y conviene entender por qué antes de
tocarlo. **ChatGPT no tiene enganches.** No es que no los hayamos puesto: no
existen. Es una aplicación cerrada, sin archivo de configuración donde declarar
un comando ni evento al que apuntarse. Todo lo que hacen Claude Code, Cursor o
Gemini —avisar de que empiezan una herramienta, pedir permiso, decir que han
terminado— aquí no está disponible por ningún camino.

Así que su estado se **mira** en vez de escucharse, leyéndole la ventana por la
capa de accesibilidad de Windows (ver :mod:`tecladoia.vigia_chatgpt`).
«Instalar» este agente no escribe ningún archivo: enciende ese vigía.

De ahí las dos consecuencias que hay que aceptar y no prometer de más:

* **No decide aprobaciones.** La palanca no gobierna a ChatGPT, porque ChatGPT
  no nos pregunta nada. La palanca sigue mandando en los agentes de línea de
  órdenes y en el envío automático tras dictar.
* **Solo hay dos momentos:** está respondiendo y ha terminado. No hay
  «esperando aprobación» ni «herramienta en curso» por separado, porque desde
  fuera de la ventana no se distinguen.

Es la mitad del semáforo, pero es la mitad que se puede sostener de verdad.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..modelo import EstadoIA
from .base import AgenteIA, EventoEnganche


class AgenteChatGPT(AgenteIA):
    id = "chatgpt"
    nombre = "ChatGPT (aplicación)"
    url_documentacion = "https://openai.com/chatgpt/download/"

    #: No llegan por enganche: los fabrica el vigía al ver cambiar la ventana.
    #: Se declaran igual para que el panel pueda enseñar sus colores y para que
    #: las reglas de comportamiento del modo 2 tengan a qué agarrarse.
    eventos = (
        EventoEnganche("ChatGPTTrabajando", "trabajando", EstadoIA.HERRAMIENTA_EN_CURSO),
        EventoEnganche("ChatGPTTerminado", "terminado", EstadoIA.TAREA_COMPLETADA),
    )

    #: Lo que este agente **no** puede hacer, para que la interfaz lo diga en
    #: vez de dejar al usuario esperando algo que no va a pasar.
    sin_enganches = True
    nota = (
        "ChatGPT no tiene enganches, así que su estado se lee mirándole la "
        "ventana. Enciende y apaga las luces del modo 2, pero no pasa por la "
        "palanca: ChatGPT no nos pide permiso para nada."
    )

    @classmethod
    def ruta_config(cls) -> Optional[Path]:
        return None  # no hay archivo que tocar

    @classmethod
    def instalado(cls) -> bool:
        from ..config import Ajustes

        try:
            if not bool(getattr(Ajustes.cargar(), "vigilar_chatgpt", True)):
                return False
        except Exception:  # noqa: BLE001 - sin configuración legible, se dirá que no
            return False
        return cls.se_puede_vigilar()

    @staticmethod
    def se_puede_vigilar() -> bool:
        """¿Está la capa de accesibilidad disponible en este equipo?"""
        import os

        if os.name != "nt":
            return False
        try:
            import comtypes.client  # noqa: F401
        except ImportError:
            return False
        return True

    @classmethod
    def _cambiar(cls, encendido: bool) -> list[str]:
        from ..config import Ajustes

        ajustes = Ajustes.cargar()
        ajustes.vigilar_chatgpt = encendido
        ajustes.guardar()
        return [
            "Vigilancia encendida: el modo de ChatGPT encenderá las luces."
            if encendido
            else "Vigilancia apagada: el modo de ChatGPT se quedará a oscuras.",
            "Hay que reiniciar el servicio para que surta efecto.",
        ]

    @classmethod
    def instalar(cls) -> list[str]:
        if not cls.se_puede_vigilar():
            return [
                "No se puede vigilar ChatGPT en este equipo: hace falta Windows "
                "y el paquete «comtypes» (se instala con «pip install comtypes»)."
            ]
        return cls._cambiar(True)

    @classmethod
    def desinstalar(cls) -> list[str]:
        return cls._cambiar(False)
