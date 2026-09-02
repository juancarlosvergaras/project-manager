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

from .config import NOMBRE, ruta_registro

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
