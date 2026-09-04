"""Punto de entrada de SikaiMini.exe.

Sin argumentos hace la instalación guiada; con argumentos se comporta como la
orden `sikaimini`, para que la tarea programada lo lance con
`SikaiMini.exe servicio`. Al terminar el asistente espera a que pulses Intro:
quien abre un `.exe` con doble clic lo hace en una ventana que se cierra sola
al acabar, y sin esa pausa no da tiempo a leer si algo falló.
"""

from __future__ import annotations

import sys


def main() -> int:
    from sikaimini.cli import main as cli

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
