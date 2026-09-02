"""MiniMic: aplicación en español para el teclado de voz de cinco teclas (Jieli 514C:8850).

Hermana de TecladoIA: reutiliza su dictado, su enfoque de ventanas y su panel, y
pone debajo un teclado distinto, que se configura por HID en vez de por Bluetooth.
"""

# COM en MTA antes de importar nada, por la misma razón que en TecladoIA: la capa
# de accesibilidad lo inicializa en STA si nadie lo dice antes, y entonces las
# llamadas asíncronas de WinRT no vuelven nunca. Aquí no hay WinRT para el
# teclado, pero sí para el audio y para quien reutilice TecladoIA al lado.
import sys as _sys

_sys.coinit_flags = 0  # type: ignore[attr-defined]

__version__ = "0.1.0"
