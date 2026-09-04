"""SikaiMini: aplicación en español para el mini teclado SiKai de tres teclas y perilla.

Tercer teclado de la casa. Lleva el mismo chip Jieli que el MiniMic —mismo
VID/PID 514C:8850 por cable y 4C4A:4155 por el receptor— y habla el mismo
protocolo, así que reutiliza ``minimic`` (protocolo, canal HID, micrófono) y
``tecladoia`` (dictado, cuadro de escribir, sonido) y pone encima lo suyo: seis
registros en vez de cinco (tres teclas y los tres gestos de la perilla), los
tipos de registro de ratón y multimedia, y las luces.
"""

# COM en MTA antes de importar nada, por la misma razón que en TecladoIA y
# MiniMic: la capa de accesibilidad lo inicializa en STA si nadie lo dice
# antes, y entonces las llamadas asíncronas de WinRT no vuelven nunca.
import sys as _sys

_sys.coinit_flags = 0  # type: ignore[attr-defined]

__version__ = "0.1.3"
