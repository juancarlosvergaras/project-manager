"""Construye TecladoIA.exe: un solo archivo, con Python dentro.

Se ejecuta con  ``python construir_exe.py``  y deja el ejecutable en
``dist/TecladoIA.exe``. Tarda un par de minutos.

Lo que importa de esta receta:

* **Un solo archivo** (``--onefile``). Un instalador que hay que descomprimir
  antes ya no es un instalador; el sentido de esto es poder mandarle a alguien
  un archivo y que lo abra.
* **La carpeta ``web`` viaja dentro** y en la misma ruta relativa, porque el
  panel la busca junto al paquete. Sin eso el ejecutable arranca y sirve un
  panel en blanco, que es de los fallos más desconcertantes.
* **``winrt`` se incluye a mano.** Sus módulos se importan por nombre en
  tiempo de ejecución, así que PyInstaller no los ve al analizar el código y
  los deja fuera. El ejecutable arrancaría y no encontraría el teclado nunca,
  sin decir por qué.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

#: Módulos que se cargan por nombre y PyInstaller no puede adivinar.
OCULTOS = [
    "winrt.windows.devices.bluetooth",
    "winrt.windows.devices.bluetooth.genericattributeprofile",
    "winrt.windows.devices.enumeration",
    "winrt.windows.storage.streams",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.system",
    "comtypes",
    "comtypes.client",
    "bleak",
]


def construir() -> int:
    orden = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "TecladoIA",
        "--console",
        "--noconfirm",
        "--clean",
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(RAIZ / "build"),
        "--specpath", str(RAIZ / "build"),
        "--paths", str(RAIZ / "src"),
        "--add-data", f"{RAIZ / 'src' / 'tecladoia' / 'web'}{';'}tecladoia/web",
    ]
    for modulo in OCULTOS:
        orden += ["--hidden-import", modulo]
    icono = RAIZ / "src" / "tecladoia" / "web" / "icono.ico"
    if icono.exists():
        orden += ["--icon", str(icono)]
    orden.append(str(RAIZ / "lanzador.py"))

    print("Construyendo TecladoIA.exe (esto tarda un par de minutos)...")
    hecho = subprocess.run(orden, cwd=RAIZ)
    if hecho.returncode != 0:
        print("La construcción falló.")
        return hecho.returncode

    exe = RAIZ / "dist" / "TecladoIA.exe"
    if not exe.exists():
        print("PyInstaller terminó pero no dejó el ejecutable donde se esperaba.")
        return 1
    print(f"Listo: {exe}  ({exe.stat().st_size / 1_048_576:.1f} MB)")
    shutil.rmtree(RAIZ / "build", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(construir())
