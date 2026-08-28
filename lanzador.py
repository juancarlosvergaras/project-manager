"""Punto de entrada del ejecutable.

`TecladoIA.exe` sin argumentos hace la instalación guiada; con argumentos se
comporta igual que la orden `tecladoia`, para que la tarea programada pueda
lanzarlo con `TecladoIA.exe servicio --host …`.

Al terminar el asistente espera a que pulses Intro. Parece un detalle tonto y
no lo es: quien abre un `.exe` con doble clic lo hace en una ventana que se
cierra sola al acabar, y sin esa pausa el programa hace su trabajo y desaparece
sin que te dé tiempo a leer si algo falló.
"""

from __future__ import annotations

import sys


def main() -> int:
    from tecladoia.cli import main as cli

    if len(sys.argv) > 1:
        return cli(sys.argv[1:])

    codigo = cli(["asistente"])
    try:
        input("  Pulsa Intro para cerrar. ")
    except (EOFError, KeyboardInterrupt):
        pass
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
