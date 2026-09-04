"""Construye SikaiMini: una carpeta con el ejecutable y Python al lado, en un zip.

``python construir_sikaimini.py`` deja ``dist/SikaiMini/SikaiMini.exe`` y
``dist/SikaiMini.zip``. Misma receta que ``construir_exe.py`` (TecladoIA) salvo
en una cosa: **carpeta, no un solo archivo**. El ``.exe`` de un solo archivo
se autoextrae al arrancar, y eso es justo lo que la heurística de Defender
(«Trojan:Win32/Bearfoos.A!ml») marca en cuanto llega descargado: el mismo
archivo escaneado en disco estaba limpio. Con la carpeta no hay
autoextracción y no salta.

* **La carpeta ``web`` de SikaiMini viaja dentro**, en la misma ruta relativa;
  sin ella el panel sale en blanco.
* **``comtypes``, ``pycaw`` y ``hid`` se incluyen a mano**: se importan dentro
  de funciones y PyInstaller no siempre los ve. Sin ``hid`` el ejecutable
  arranca y nunca encuentra el teclado; sin ``pycaw`` nunca adopta el micrófono.
* No lleva ``winrt`` ni ``bleak``: SikaiMini no usa Bluetooth.
* **``minimic`` va dentro**: SikaiMini importa su protocolo y su canal HID.
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
    # SikaiMini se apoya en MiniMic (protocolo, canal HID, micrófono, ficha de programas).
    "minimic", "minimic.protocolo", "minimic.dispositivo", "minimic.config",
]


LEEME = """SikaiMini

Deja esta carpeta entera donde quieras tenerla (por ejemplo en Documentos)
y abre SikaiMini.exe. Hace la instalación guiada: crea la tarea que lo arranca
con Windows y lo pone en marcha. El panel queda en http://127.0.0.1:8772

No muevas ni borres la carpeta _internal: es el Python que lleva dentro.
"""


def construir() -> int:
    orden = [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--name", "SikaiMini", "--console", "--noconfirm", "--clean",
        "--distpath", str(RAIZ / "dist"),
        "--workpath", str(RAIZ / "build"),
        "--specpath", str(RAIZ / "build"),
        "--paths", str(RAIZ / "src"),
        "--add-data", f"{RAIZ / 'src' / 'sikaimini' / 'web'};sikaimini/web",
        "--collect-submodules", "comtypes",
    ]
    for modulo in OCULTOS:
        orden += ["--hidden-import", modulo]
    orden.append(str(RAIZ / "lanzador_sikaimini.py"))

    print("Construyendo SikaiMini.exe (tarda un par de minutos)...")
    hecho = subprocess.run(orden, cwd=RAIZ)
    if hecho.returncode != 0:
        print("La construcción falló.")
        return hecho.returncode
    carpeta = RAIZ / "dist" / "SikaiMini"
    exe = carpeta / "SikaiMini.exe"
    if not exe.exists():
        print("PyInstaller terminó pero no dejó el ejecutable donde se esperaba.")
        return 1
    (carpeta / "LEEME.txt").write_text(LEEME, encoding="utf-8")
    sys.path.insert(0, str(RAIZ / "src"))
    from sikaimini.empaquetado import NOMBRE_EXE

    for viejo in (RAIZ / "dist").glob("SikaiMini-*.zip"):
        viejo.unlink()
    zip_final = RAIZ / "dist" / NOMBRE_EXE
    shutil.make_archive(str(zip_final.with_suffix("")), "zip", RAIZ / "dist", "SikaiMini")
    # Y una copia con el nombre de siempre, para los enlaces que no saben de versiones.
    shutil.copyfile(zip_final, RAIZ / "dist" / "SikaiMini.zip")
    print(f"Listo: {zip_final}  ({zip_final.stat().st_size / 1_048_576:.1f} MB)")
    shutil.rmtree(RAIZ / "build", ignore_errors=True)
    viejo = RAIZ / "dist" / "SikaiMini.exe"
    if viejo.exists():
        viejo.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(construir())
