"""Construye la Botonera: una carpeta con el ejecutable y Python al lado, en un zip.

``python construir_botonera.py`` deja ``dist/Botonera/Botonera.exe`` y
``dist/Botonera-<versión>.zip`` (más la copia ``Botonera.zip`` para los enlaces
fijos). Misma receta que SikaiMini: **carpeta, no un solo archivo**, para que
Defender no marque la autoextracción.

* **La carpeta ``web`` viaja dentro**, en la misma ruta relativa.
* **``hid`` y ``comtypes`` se incluyen a mano**: se importan dentro de
  funciones. Sin ``hid`` el ejecutable arranca y nunca encuentra el teclado;
  sin ``comtypes`` la tecla de dictado no encuentra el botón de Claude.
* **``minimic``, ``sikaimini`` y ``tecladoia`` van dentro**: la Botonera toma
  de ellos el canal HID, las tablas de teclas, el túnel y el dictado.
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
    "tecladoia.dictado", "tecladoia.cuadro_de_texto", "tecladoia.sonido", "tecladoia.sucesos", "tecladoia.registro",
    "tecladoia.enfoque", "tecladoia.microfono_propio",
    "minimic", "minimic.protocolo", "minimic.dispositivo", "minimic.config", "minimic.tunel",
    "sikaimini.protocolo",
    "botonera.asistente", "botonera.lanzador", "botonera.escucha",
]

LEEME = """Botonera

Deja esta carpeta entera donde quieras tenerla (por ejemplo en Documentos)
y abre Botonera.exe. Hace la instalación guiada: crea la tarea que lo arranca
con Windows y lo pone en marcha. El panel queda en http://127.0.0.1:8773

No muevas ni borres la carpeta _internal: es el Python que lleva dentro.
"""


def construir() -> int:
    orden = [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--name", "Botonera", "--console", "--noconfirm", "--clean",
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(RAIZ / "build"),
        "--specpath", str(RAIZ / "build"),
        "--paths", str(RAIZ / "src"),
        "--add-data", f"{RAIZ / 'src' / 'botonera' / 'web'};botonera/web",
        "--collect-submodules", "comtypes",
    ]
    for modulo in OCULTOS:
        orden += ["--hidden-import", modulo]
    orden.append(str(RAIZ / "lanzador_botonera.py"))

    print("Construyendo Botonera.exe (tarda un par de minutos)...")
    hecho = subprocess.run(orden, cwd=RAIZ)
    if hecho.returncode != 0:
        print("La construcción falló.")
        return hecho.returncode
    carpeta = RAIZ / "dist" / "Botonera"
    exe = carpeta / "Botonera.exe"
    if not exe.exists():
        print("PyInstaller terminó pero no dejó el ejecutable donde se esperaba.")
        return 1
    (carpeta / "LEEME.txt").write_text(LEEME, encoding="utf-8")
    sys.path.insert(0, str(RAIZ / "src"))
    from botonera.empaquetado import NOMBRE_EXE

    for viejo in (RAIZ / "dist").glob("Botonera-*.zip"):
        viejo.unlink()
    zip_final = RAIZ / "dist" / NOMBRE_EXE
    shutil.make_archive(str(zip_final.with_suffix("")), "zip", RAIZ / "dist", "Botonera")
    shutil.copyfile(zip_final, RAIZ / "dist" / "Botonera.zip")
    print(f"Listo: {zip_final}  ({zip_final.stat().st_size / 1_048_576:.1f} MB)")
    shutil.rmtree(RAIZ / "build", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(construir())
