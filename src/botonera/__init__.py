"""Botonera: aplicación en español para el teclado de 12 teclas, 3 perillas y luces.

Cuarto teclado de la casa. Mismo chip Jieli que el MiniMic y el SiKai mini
(``514C:8850`` por cable, «MINI_KEYBOARD» por Bluetooth) pero otro firmware,
el de los teclados macro «ch57x»: solo escritura, sin suma de control, con
tres perfiles que se cambian con un botón del propio teclado y luces RGB.
El fabricante no da programa; este lo sustituye.
"""

# COM en MTA antes de importar nada, por la misma razón que en las otras tres:
# la capa de accesibilidad (con la que se pulsa el botón de dictado de Claude
# o ChatGPT) lo inicializa en STA si nadie lo dice antes.
import sys as _sys

_sys.coinit_flags = 0  # type: ignore[attr-defined]

__version__ = "0.3.0"
