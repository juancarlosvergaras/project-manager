"""Que MiniMic arranque con Windows: la tarea programada.

Misma receta que TecladoIA, con su nombre, su registro y su orden. Dos
disparadores —al iniciar sesión y cada diez minutos— y `pythonw.exe` para que
no haya consola a la que mandar un ``^C``. Repetir el disparador es inofensivo
porque el servicio se niega a arrancar si ya hay otro vivo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import NOMBRE, Ajustes, ruta_config, ruta_registro

TAREA = NOMBRE  # «MiniMic»


def orden_de_arranque() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    interprete = Path(sys.executable).resolve()
    sin_consola = interprete.with_name("pythonw.exe")
    if os.name == "nt" and sin_consola.is_file():
        interprete = sin_consola
    return f'"{interprete}" -m minimic'


def registrar_tarea(host: str = "", directorio: Path | None = None) -> tuple[bool, str]:
    """Deja el servicio arrancando al iniciar sesión. Devuelve (hecho, explicación)."""
    if os.name != "nt":
        return False, "las tareas programadas son cosa de Windows"
    registro = ruta_registro()
    registro.parent.mkdir(parents=True, exist_ok=True)
    argumentos = "servicio" + (f" --host {host}" if host else "")
    # Las comillas van tal cual, sin barras: `cmd` no entiende `\"`, y con
    # ellas el comando entero queda inválido y la tarea dispara sin arrancar nada.
    orden = f'/c start /min "" cmd /c "{orden_de_arranque()} {argumentos} >> "{registro}" 2>&1"'
    guion = (
        f"$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '{orden}' "
        f"-WorkingDirectory '{directorio or Path.cwd()}';"
        "$d = New-ScheduledTaskTrigger -AtLogOn -User ($env:USERDOMAIN + '\\' + $env:USERNAME);"
        "$d.Delay = 'PT25S';"
        "$r = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) "
        "-RepetitionInterval (New-TimeSpan -Minutes 10);"
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 "
        "-RestartInterval ([TimeSpan]::FromMinutes(1));"
        f"Register-ScheduledTask -TaskName '{TAREA}' -Action $a -Trigger @($d, $r) -Settings $s -Force | Out-Null"
    )
    try:
        hecho = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True, timeout=60)
    except Exception as error:  # noqa: BLE001
        return False, str(error)
    if hecho.returncode != 0:
        return False, (hecho.stderr or hecho.stdout).strip()[-400:] or "PowerShell no dijo por qué"
    return True, f"tarea «{TAREA}» creada: arranca al iniciar sesión y se revisa cada diez minutos"


def quitar_tarea() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "las tareas programadas son cosa de Windows"
    hecho = subprocess.run(["schtasks", "/Delete", "/TN", TAREA, "/F"], capture_output=True, text=True)
    return hecho.returncode == 0, (hecho.stdout or hecho.stderr).strip()


def hay_tarea() -> bool:
    if os.name != "nt":
        return False
    hecho = subprocess.run(["schtasks", "/Query", "/TN", TAREA], capture_output=True, text=True)
    return hecho.returncode == 0


def acceso_directo_en_el_escritorio(url: str) -> str:
    """Deja un «.url» con el nombre de la aplicación en el escritorio apuntando al panel local. Devuelve la ruta o «»."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(0, 0x10, 0, 0, buf)  # CSIDL_DESKTOPDIRECTORY
        escritorio = Path(buf.value) if buf.value else Path.home() / "Desktop"
        destino = escritorio / f"{NOMBRE}.url"
        destino.write_text(f"[InternetShortcut]
URL={url}
IconIndex=0
", encoding="utf-8")
        return str(destino)
    except Exception:  # noqa: BLE001 - un escritorio raro no debe tumbar la instalación
        return ""


def abrir_en_el_navegador(url: str) -> bool:
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001
        return False


def ejecutar(preguntar=input, escribir=print) -> int:
    """La instalación guiada: lo que hace `MiniMic.exe` al abrirse sin argumentos."""
    from . import dispositivo

    escribir("")
    escribir(f"  {NOMBRE} — instalación")
    escribir("  " + "-" * 22)
    escribir("")
    escribir("  La aplicación en español para el teclado de voz de cinco teclas.")
    escribir("")

    ajustes = Ajustes.cargar()

    escribir("==> Buscando el teclado")
    try:
        p = dispositivo.presencia()
        if p.conectado:
            escribir(f"    [ok] {p.descripcion}")
            if not p.configurable:
                escribir("         Por el receptor funciona; para grabarle las teclas conéctalo por cable una vez.")
        else:
            escribir("    [!]  no lo veo. Enchufa el cable o el receptor; la instalación sigue igual.")
    except dispositivo.ErrorDispositivo as error:
        escribir(f"    [!]  {error}")

    escribir("")
    escribir("==> Clave del panel")
    escribir("    Sin clave el panel solo se abre en este equipo. Con ella se puede publicar.")
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
    escribir("==> Dejando el servicio arrancando con el equipo")
    hecho, detalle = registrar_tarea(ajustes.host_panel if ajustes.host_panel != "127.0.0.1" else "")
    escribir(("    [ok] " if hecho else "    [!]  ") + detalle)
    if hecho:
        arrancado = subprocess.run(["schtasks", "/Run", "/TN", TAREA], capture_output=True, text=True).returncode == 0
        escribir("    [ok] servicio arrancado" if arrancado else "    [!]  no se pudo arrancar ahora; arrancará al iniciar sesión")
    else:
        escribir(f"    Puedes arrancarlo a mano: {orden_de_arranque()} servicio")

    escribir("")
    escribir("==> Listo")
    escribir(f"    Configuración en {ruta_config()}")
    # El panel de este equipo es el camino principal: no depende de Internet
    # ni de ningún otro ordenador. Se deja a mano y se abre.
    local = f"http://127.0.0.1:{ajustes.puerto_panel}/"
    acceso = acceso_directo_en_el_escritorio(local)
    if acceso:
        escribir(f"    [ok] acceso directo al panel en el escritorio: {acceso}")
    escribir(f"    El panel de este equipo: {local}  (sin clave desde aquí)")
    if ajustes.host_panel not in ("", "127.0.0.1"):
        escribir(f"    Y desde fuera, con clave: http://{ajustes.host_panel}:{ajustes.puerto_panel}")
    if hecho and abrir_en_el_navegador(local):
        escribir("    [ok] abierto en el navegador")
    escribir("")
    escribir("    La tecla blanca abre el dictado en el programa que elijas en el panel.")
    escribir("    Conecta el teclado por cable una vez para que se le graben las teclas.")
    escribir("")
    return 0
