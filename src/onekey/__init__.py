"""OneKey: aplicación en español para el botón Bluetooth de una tecla (AI_VOICE).

Quinto teclado de la casa: una caja con un solo botón, micrófono manos libres,
luz e interruptor, por Bluetooth clásico. El botón manda Alt derecho y por
Bluetooth no se le puede cambiar, así que OneKey no lo remapea: **reconoce de
qué aparato viene la pulsación** (``minimic.boton``, por Raw Input) y solo la
suya abre o cierra el dictado, con el mismo ``tecladoia.dictado`` que los
demás teclados. Su micrófono manos libres se adopta como el del sistema.
"""

# COM en MTA antes de importar nada, por la misma razón que en TecladoIA y
# MiniMic: la capa de accesibilidad lo inicializa en STA si nadie lo dice
# antes, y entonces las llamadas asíncronas de WinRT no vuelven nunca.
import sys as _sys

_sys.coinit_flags = 0  # type: ignore[attr-defined]

__version__ = "0.1.0"
