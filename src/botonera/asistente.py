"""La instalación guiada: lo que hace ``Botonera.exe`` al abrirse sin argumentos.

Misma receta que SikaiMini: para el servicio anterior, graba el teclado si está
por cable, pregunta por la clave y por Tailscale, crea la tarea programada,
arranca el servicio él mismo, deja un acceso directo al panel en el escritorio
y lo abre cuando ``/api/salud`` contesta.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .cli import TAREA, orden_de_arranque, registrar_tarea
from .config import NOMBRE, Ajustes, ruta_config, ruta_registro


def acceso_directo_en_el_escritorio(url: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(0, 0x10, 0, 0, buf)  # CSIDL_DESKTOPDIRECTORY
        escritorio = Path(buf.value) if buf.value else Path.home() / "Desktop"
        destino = escritorio / f"{NOMBRE}.url"
        destino.write_text(f"[InternetShortcut]\nURL={url}\nIconIndex=0\n", encoding="utf-8")
        return str(destino)
    except Exception:  # noqa: BLE001
        return ""


def abrir_en_el_navegador(url: str) -> bool:
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001
        return False


def grabar_el_teclado(ajustes: Ajustes, escribir=print) -> None:
    """Graba los tres perfiles ahí mismo, sin esperar al servicio."""
    from . import dispositivo
    from .servicio import Servicio

    try:
        servicio = Servicio(ajustes)
        servicio.estado.presencia = dispositivo.presencia()
        r = servicio.aplicar()
        if r.get("escrito"):
            escribir(f"    [ok] teclado grabado: tres perfiles, {r.get('mensajes')} mensajes")
        else:
            escribir(f"    [!]  {r.get('aviso')}")
    except Exception as error:  # noqa: BLE001
        escribir(f"    [!]  no se pudo grabar ahora ({error}); el servicio lo hará al conectarlo")


def detener_servicios_anteriores() -> int:
    """Para cualquier botonera servicio que quede vivo. Devuelve cuántos paró."""
    if os.name != "nt":
        return 0
    guion = (
        "$mio = $PID; Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -like 'python*' -or $_.Name -like 'botonera*') -and $_.ProcessId -ne $mio "
        "-and $_.CommandLine -like '*botonera*servicio*' } | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    try:
        hecho = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True, timeout=40)
    except Exception:  # noqa: BLE001
        return 0
    subprocess.run(["schtasks", "/End", "/TN", TAREA], capture_output=True, text=True)
    return len([l for l in hecho.stdout.split() if l.strip().isdigit()])


def arrancar_ahora(host: str = "") -> bool:
    if os.name != "nt":
        return False
    registro = ruta_registro()
    registro.parent.mkdir(parents=True, exist_ok=True)
    orden = f'{orden_de_arranque()} servicio' + (f" --host {host}" if host else "")
    try:
        with open(registro, "ab") as salida:
            subprocess.Popen(
                orden, shell=True, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                cwd=str(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()),
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def esperar_al_servicio(puerto: int, plazo_s: float = 30.0) -> str:
    import json
    import time
    import urllib.request

    limite = time.monotonic() + plazo_s
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=2) as r:
                datos = json.loads(r.read().decode("utf-8"))
            if isinstance(datos, dict) and datos.get("app") == "botonera":
                return str(datos.get("version") or "?")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return ""


def ejecutar(preguntar=input, escribir=print) -> int:
    from . import dispositivo

    escribir("")
    escribir(f"  {NOMBRE} — instalación")
    escribir("  " + "-" * 22)
    escribir("")
    escribir("  La aplicación en español para el teclado de 12 teclas, 3 perillas y luces.")
    escribir("")

    ajustes = Ajustes.cargar()

    escribir("==> Buscando el teclado")
    try:
        p = dispositivo.presencia()
        if p.conectado:
            escribir(f"    [ok] {p.descripcion}")
            if p.configurable:
                grabar_el_teclado(ajustes, escribir)
            else:
                escribir("         Por Bluetooth funciona; para grabarle los perfiles conéctalo por cable una vez.")
        elif p.otro_jieli:
            escribir("    [!]  el teclado Jieli que hay por cable es otro (MiniMic o SiKai); la instalación sigue igual.")
        else:
            escribir("    [!]  no lo veo. Conéctalo por cable o por Bluetooth; la instalación sigue igual.")
    except dispositivo.ErrorDispositivo as error:
        escribir(f"    [!]  {error}")

    escribir("")
    escribir("==> Clave del panel")
    escribir("    Sin clave el panel solo se abre en este equipo. Con ella se publica en ledblanco.proyectoia.org.")
    if ajustes.clave_panel:
        pregunta = f"    Ya hay una ({len(ajustes.clave_panel)} caracteres). Otra, o Intro para dejarla: "
    else:
        pregunta = "    Escribe una clave (Intro para dejarlo solo en este PC): "
    try:
        nueva = (preguntar(pregunta) or "").strip()
    except (EOFError, KeyboardInterrupt):
        nueva = ""
    if nueva:
        ajustes.clave_panel = nueva
        ajustes.guardar()
        escribir("    [ok] clave guardada")

    escribir("")
    escribir("==> Dónde escucha el panel")
    from .panel import direcciones_locales

    tailscale = [d for d in direcciones_locales() if d.startswith("100.")]
    if not ajustes.clave_panel:
        escribir("    Sin clave, solo en este equipo (http://127.0.0.1:%d)." % ajustes.puerto_panel)
    elif not tailscale:
        escribir("    No veo Tailscale en este equipo; el panel queda en http://127.0.0.1:%d." % ajustes.puerto_panel)
        escribir("    Con Tailscale instalado, ledblanco.proyectoia.org pasaría a este equipo.")
    else:
        direccion = tailscale[0]
        escribir(f"    Este equipo tiene Tailscale en {direccion}. Con la clave puesta, se presenta solo al")
        escribir("    portero y ledblanco.proyectoia.org pasa a este equipo cuando tenga el teclado.")
        try:
            respuesta = (preguntar(f"    ¿Publicar también el panel en {direccion}? [S/n]: ") or "s").strip().lower()
        except (EOFError, KeyboardInterrupt):
            respuesta = "s"
        if respuesta.startswith("s"):
            ajustes.host_panel = direccion
            ajustes.guardar()
            escribir(f"    [ok] el panel escuchará en http://{direccion}:{ajustes.puerto_panel}")
            escribir("         Si Windows pregunta si permite a la Botonera en la red, di que sí.")
        else:
            ajustes.host_panel = "127.0.0.1"
            ajustes.guardar()

    escribir("")
    escribir("==> Parando lo que hubiera de antes")
    parados = detener_servicios_anteriores()
    escribir(f"    [ok] {parados} servicio(s) anterior(es) parado(s)" if parados else "    [ok] no había ninguno")

    escribir("")
    escribir("==> Dejando el servicio arrancando con el equipo")
    host_publico = ajustes.host_panel if ajustes.host_panel != "127.0.0.1" else ""
    hecho, detalle = registrar_tarea(host_publico)
    escribir(("    [ok] " if hecho else "    [!]  ") + detalle)
    if arrancar_ahora(host_publico):
        escribir("    … arrancando el servicio")
        version = esperar_al_servicio(ajustes.puerto_panel)
        if version:
            escribir(f"    [ok] el servicio contesta: {NOMBRE} {version}")
        else:
            escribir(f"    [!]  el servicio no contesta en 30 s; mira {ruta_registro()}")
    elif hecho:
        subprocess.run(["schtasks", "/Run", "/TN", TAREA], capture_output=True, text=True)
        escribir("    [ok] se le pidió arrancar a la tarea programada")
    else:
        escribir(f"    Puedes arrancarlo a mano: {orden_de_arranque()} servicio")

    escribir("")
    escribir("==> Listo")
    escribir(f"    Configuración en {ruta_config()}")
    local = f"http://127.0.0.1:{ajustes.puerto_panel}/"
    acceso = acceso_directo_en_el_escritorio(local)
    if acceso:
        escribir(f"    [ok] acceso directo al panel en el escritorio: {acceso}")
    escribir(f"    El panel de este equipo: {local}  (sin clave desde aquí)")
    if ajustes.host_panel not in ("", "127.0.0.1"):
        escribir(f"    Y desde fuera, con clave: http://{ajustes.host_panel}:{ajustes.puerto_panel}")
    if esperar_al_servicio(ajustes.puerto_panel, 5.0) and abrir_en_el_navegador(local):
        escribir("    [ok] abierto en el navegador")
    escribir("")
    escribir("    La tecla 1 abre el dictado del programa que tengas delante (Claude, ChatGPT…).")
    escribir("    Conecta el teclado por cable una vez para que se le graben los tres perfiles.")
    escribir("")
    return 0
