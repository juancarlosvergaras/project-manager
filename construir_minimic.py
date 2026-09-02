"""Construye MiniMic.exe: un solo archivo, con Python dentro.

``python construir_minimic.py`` deja ``dist/MiniMic.exe``. Misma receta que
``construir_exe.py`` (TecladoIA), con lo que MiniMic necesita:

* **La carpeta ``web`` de MiniMic viaja dentro**, en la misma ruta relativa;
  sin ella el panel sale en blanco.
* **``comtypes``, ``pycaw`` y ``hid`` se incluyen a mano**: se importan dentro
  de funciones y PyInstaller no siempre los ve. Sin ``hid`` el ejecutable
  arranca y nunca encuentra el teclado; sin ``pycaw`` nunca adopta el micrófono.
* No lleva ``winrt`` ni ``bleak``: MiniMic no usa Bluetooth.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

OCULTOS = [
    "hid",
    "comtypes", "comtypes.client", "comtypes.automation",
    "pycaw", "pycaw.utils", "pycaw.constants", "pycaw.api.policyconfig", "pycaw.api.mmdeviceapi",
    "pycaw.api.mmdeviceapi.depend", "pycaw.api.mmdeviceapi.depend.structures",
    "tecladoia.dictado", "tecladoia.cuadro_de_texto", "tecladoia.sonido", "tecladoia.sucesos", "tecladoia.registro",
]


def construir() -> int:
    orden = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", "MiniMic", "--console", "--noconfirm", "--clean",
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(RAIZ / "build"),
        "--specpath", str(RAIZ / "build"),
        "--paths", str(RAIZ / "src"),
        "--add-data", f"{RAIZ / 'src' / 'minimic' / 'web'};minimic/web",
        "--collect-submodules", "comtypes",
    ]
    for modulo in OCULTOS:
        orden += ["--hidden-import", modulo]
    orden.append(str(RAIZ / "lanzador_minimic.py"))

    print("Construyendo MiniMic.exe (tarda un par de minutos)...")
    hecho = subprocess.run(orden, cwd=RAIZ)
    if hecho.returncode != 0:
        print("La construcción falló.")
        return hecho.returncode
    exe = RAIZ / "dist" / "MiniMic.exe"
    if not exe.exists():
        print("PyInstaller terminó pero no dejó el ejecutable donde se esperaba.")
        return 1
    print(f"Listo: {exe}  ({exe.stat().st_size / 1_048_576:.1f} MB)")
    shutil.rmtree(RAIZ / "build", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(construir())
