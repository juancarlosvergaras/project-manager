"""Que OneKey arranque con Windows: la tarea programada, sin ventanas.

Misma receta que los demás teclados, con una cosa aprendida el 21/9/2026: el
ejecutable con consola (el de la instalación guiada) **no** es el que debe
lanzar la tarea. Cada disparador de diez minutos lo abría, el servicio veía que
ya había otro y se retiraba, y ese arranque era una ventana de DOS que asomaba
cada rato. La carpeta trae dos ejecutables sobre el mismo Python:
``OneKey.exe`` (con consola, para instalar y mirar) y ``OneKeyServicio.exe``
(sin ventana), y la tarea usa el segundo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import NOMBRE, Ajustes, ruta_config, ruta_registro

TAREA = NOMBRE  # «OneKey»
EJECUTABLE_SIN_VENTANA = "OneKeyServicio.exe"


def ejecutable_sin_ventana() -> Path | None:
    """El ejecutable sin consola de la misma carpeta, si lo hay."""
    if not getattr(sys, "frozen", False):
        return None
    candidato = Path(sys.executable).resolve().with_name(EJECUTABLE_SIN_VENTANA)
    return candidato if candidato.is_file() else None


def ejecutable_y_argumentos(argumentos: str = "") -> tuple[str, str]:
    """Qué programa lanza la tarea y con qué argumentos, **sin consola**."""
    if getattr(sys, "frozen", False):
        exe = ejecutable_sin_ventana() or Path(sys.executable).resolve()
        return str(exe), argumentos.strip()
    interprete = Path(sys.executable).resolve()
    sin_consola = interprete.with_name("pythonw.exe")
    if os.name == "nt" and sin_consola.is_file():
        interprete = sin_consola
    return str(interprete), f"-m onekey {argumentos}".strip()


def orden_de_arranque() -> str:
    ejecutable, argumentos = ejecutable_y_argumentos()
    return f'"{ejecutable}"' + (f" {argumentos}" if argumentos else "")


def registrar_tarea(host: str = "", directorio: Path | None = None) -> tuple[bool, str]:
    """Deja el servicio arrancando al iniciar sesión. Devuelve (hecho, explicación)."""
    if os.name != "nt":
        return False, "las tareas programadas son cosa de Windows"
    registro = ruta_registro()
    registro.parent.mkdir(parents=True, exist_ok=True)
    argumentos = "servicio" + (f" --host {host}" if host else "")
    ejecutable, arg_tarea = ejecutable_y_argumentos(argumentos)
    guion = (
        f"$a = New-ScheduledTaskAction -Execute '{ejecutable}' -Argument '{arg_tarea}' "
        f"-WorkingDirectory '{directorio or Path(ejecutable).parent}';"
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
        hecho = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as error:  # noqa: BLE001
        return False, str(error)
    if hecho.returncode != 0:
        return False, (hecho.stderr or hecho.stdout).strip()[-400:] or "PowerShell no dijo por qué"
    return True, f"tarea «{TAREA}» creada: arranca al iniciar sesión y se revisa cada diez minutos, sin ventana"


def quitar_tarea() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "las tareas programadas son cosa de Windows"
    hecho = subprocess.run(["schtasks", "/Delete", "/TN", TAREA, "/F"], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return hecho.returncode == 0, (hecho.stdout or hecho.stderr).strip()


def hay_tarea() -> bool:
    if os.name != "nt":
        return False
    hecho = subprocess.run(["schtasks", "/Query", "/TN", TAREA], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return hecho.returncode == 0


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


def detener_servicios_anteriores() -> int:
    """Para cualquier OneKey servicio que quede vivo. Devuelve cuántos paró."""
    if os.name != "nt":
        return 0
    guion = (
        "$mio = $PID; Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -like 'python*' -or $_.Name -like 'onekey*') -and $_.ProcessId -ne $mio "
        "-and $_.CommandLine -like '*onekey*servicio*' } | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    try:
        hecho = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True, timeout=40,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:  # noqa: BLE001
        return 0
    subprocess.run(["schtasks", "/End", "/TN", TAREA], capture_output=True, text=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return len([l for l in hecho.stdout.split() if l.strip().isdigit()])


def arrancar_ahora(host: str = "") -> bool:
    """Arranca el servicio ya, sin esperar al programador de tareas ni abrir ventana."""
    if os.name != "nt":
        return False
    ejecutable, argumentos = ejecutable_y_argumentos("servicio" + (f" --host {host}" if host else ""))
    try:
        subprocess.Popen(
            [ejecutable, *argumentos.split()] if argumentos else [ejecutable],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=str(Path(ejecutable).parent),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def esperar_al_servicio(puerto: int, plazo_s: float = 30.0) -> str:
    """Devuelve la versión que contesta en /api/salud, o «» si no llega a tiempo."""
    import json
    import time
    import urllib.request

    limite = time.monotonic() + plazo_s
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=2) as r:
                datos = json.loads(r.read().decode("utf-8"))
            if isinstance(datos, dict) and datos.get("app") == "onekey":
                return str(datos.get("version") or "?")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return ""


def ejecutar(preguntar=input, escribir=print) -> int:
    """La instalación guiada: lo que hace `OneKey.exe` al abrirse sin argumentos."""
    from minimic import boton

    escribir("")
    escribir(f"  {NOMBRE} — instalación")
    escribir("  " + "-" * 22)
    escribir("")
    escribir("  La aplicación en español para el botón Bluetooth de una tecla con micrófono (AI_VOICE).")
    escribir("")

    ajustes = Ajustes.cargar()

    escribir("==> Buscando el botón")
    try:
        b = boton.buscar(ajustes.boton_bluetooth)
        if b:
            escribir(f"    [ok] {b.descripcion}")
        else:
            escribir(f"    [!]  no veo «{ajustes.boton_bluetooth}». Enciéndelo y emparéjalo en Configuración › Bluetooth;")
            escribir("         la instalación sigue igual y el servicio lo cogerá en cuanto aparezca.")
    except Exception as error:  # noqa: BLE001
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
    escribir("==> onekey.proyectoia.org")
    from .panel import direcciones_locales

    tailscale = [d for d in direcciones_locales() if d.startswith("100.")]
    if not ajustes.clave_panel:
        escribir("    Sin clave, el panel queda solo en este equipo (http://127.0.0.1:%d)." % ajustes.puerto_panel)
    elif not tailscale:
        escribir("    No veo Tailscale en este equipo; el panel queda en http://127.0.0.1:%d." % ajustes.puerto_panel)
        escribir("    Con Tailscale instalado, onekey.proyectoia.org pasaría a este equipo.")
    else:
        escribir(f"    Este equipo tiene Tailscale ({tailscale[0]}): el servicio se presenta solo al portero")
        escribir("    del Mac mini y onekey.proyectoia.org pasa a este equipo cuando tenga el botón.")

    escribir("")
    escribir("==> Parando lo que hubiera de antes")
    parados = detener_servicios_anteriores()
    escribir(f"    [ok] {parados} servicio(s) anterior(es) parado(s)" if parados else "    [ok] no había ninguno")

    escribir("")
    escribir("==> Dejando el servicio arrancando con el equipo")
    hecho, detalle = registrar_tarea()
    escribir(("    [ok] " if hecho else "    [!]  ") + detalle)
    if arrancar_ahora():
        escribir("    … arrancando el servicio")
        version = esperar_al_servicio(ajustes.puerto_panel)
        if version:
            escribir(f"    [ok] el servicio contesta: {NOMBRE} {version}")
        else:
            escribir(f"    [!]  el servicio no contesta en 30 s; mira {ruta_registro()}")
    elif hecho:
        subprocess.run(["schtasks", "/Run", "/TN", TAREA], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
    if esperar_al_servicio(ajustes.puerto_panel, 5.0) and abrir_en_el_navegador(local):
        escribir("    [ok] abierto en el navegador")
    escribir("")
    escribir("    Pulsa el botón: se abre el dictado en el programa que elijas en el panel.")
    escribir("    Vuelve a pulsarlo: se cierra y el texto entra.")
    escribir("")
    return 0
