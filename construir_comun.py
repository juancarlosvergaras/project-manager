"""La receta común para construir un teclado: una carpeta con dos ejecutables.

``construir_carpeta(...)`` deja ``dist/<Nombre>/`` con:

* ``<Nombre>.exe`` **con consola**: la instalación guiada, para abrir con
  doble clic y leer lo que dice.
* ``<Nombre>Servicio.exe`` **sin ventana**: el que lanza la tarea programada.
  Con el de consola, cada disparador de diez minutos abría una ventana de DOS
  (el servicio veía que ya había otro y se retiraba, pero la ventana ya había
  asomado). Cuatro teclados, una ventana cada dos minutos y medio (21/9/2026).

Los dos comparten el mismo ``_internal`` (PyInstaller lo permite con una
``.spec`` de dos ``EXE`` y un ``COLLECT``), así que la carpeta pesa lo mismo
que antes. Y es una carpeta, no un solo archivo: el ``.exe`` de un solo
archivo se autoextrae al arrancar y eso es lo que la heurística de Defender
marca en cuanto llega descargado.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

_PLANTILLA = """# -*- mode: python ; coding: utf-8 -*-
# Generado por construir_comun.py; no editar a mano.
a = Analysis(
    [{lanzador!r}],
    pathex=[{src!r}],
    binaries=[],
    datas={datas!r},
    hiddenimports={ocultos!r},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe_consola = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name={nombre!r},
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False, argv_emulation=False,
)
exe_servicio = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name={nombre_servicio!r},
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
)
coll = COLLECT(
    exe_consola, exe_servicio, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[], name={nombre!r},
)
"""


def construir_carpeta(
    nombre: str,
    lanzador: str,
    datas: list[tuple[str, str]],
    ocultos: list[str],
    leeme: str,
    nombre_zip: str,
    collect_submodules: tuple[str, ...] = ("comtypes",),
) -> int:
    """Construye ``dist/<nombre>/`` y ``dist/<nombre_zip>`` (más ``<nombre>.zip``). Devuelve el código de salida."""
    ocultos = list(ocultos)
    for paquete in collect_submodules:
        ocultos += _submodulos(paquete)
    spec = RAIZ / "build" / f"{nombre}.spec"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(_PLANTILLA.format(
        lanzador=str(RAIZ / lanzador), src=str(RAIZ / "src"),
        datas=[(str(RAIZ / origen), destino) for origen, destino in datas],
        ocultos=sorted(set(ocultos)), nombre=nombre, nombre_servicio=f"{nombre}Servicio",
    ), encoding="utf-8")
    orden = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(RAIZ / "dist"), "--workpath", str(RAIZ / "build"), str(spec),
    ]
    print(f"Construyendo {nombre}.exe y {nombre}Servicio.exe (tarda un par de minutos)...")
    hecho = subprocess.run(orden, cwd=RAIZ)
    if hecho.returncode != 0:
        print("La construcción falló.")
        return hecho.returncode
    carpeta = RAIZ / "dist" / nombre
    for exe in (f"{nombre}.exe", f"{nombre}Servicio.exe"):
        if not (carpeta / exe).exists():
            print(f"PyInstaller terminó pero no dejó {exe} donde se esperaba.")
            return 1
    (carpeta / "LEEME.txt").write_text(leeme, encoding="utf-8")
    for viejo in (RAIZ / "dist").glob(f"{nombre}-*.zip"):
        viejo.unlink()
    zip_final = RAIZ / "dist" / nombre_zip
    shutil.make_archive(str(zip_final.with_suffix("")), "zip", RAIZ / "dist", nombre)
    shutil.copyfile(zip_final, RAIZ / "dist" / f"{nombre}.zip")
    print(f"Listo: {zip_final}  ({zip_final.stat().st_size / 1_048_576:.1f} MB)")
    shutil.rmtree(RAIZ / "build", ignore_errors=True)
    return 0


def _submodulos(paquete: str) -> list[str]:
    """Todos los submódulos de un paquete instalado (lo que hacía --collect-submodules)."""
    import importlib
    import pkgutil

    try:
        modulo = importlib.import_module(paquete)
    except Exception:  # noqa: BLE001
        return [paquete]
    nombres = [paquete]
    ruta = getattr(modulo, "__path__", None)
    if ruta:
        for info in pkgutil.walk_packages(ruta, prefix=paquete + "."):
            nombres.append(info.name)
    return nombres
