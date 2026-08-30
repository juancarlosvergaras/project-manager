"""El paso a paso que ve quien abre TecladoIA.exe.

El `.exe` lleva Python dentro, así que en el ordenador nuevo no hace falta
instalar nada antes. Esa es su razón de ser: `instalar.ps1` funciona bien, pero
empieza por comprobar que hay Python y esa comprobación falla justo en los
equipos donde más falta hace la ayuda.

Hace lo mismo que el script, en el mismo orden y con las mismas cautelas:

1. Comprueba que el teclado esté emparejado, y avisa si no. **Emparejar es lo
   único que no se puede automatizar**: Windows exige confirmarlo a mano.
2. Pide la clave del panel, ofreciendo la que ya hubiera.
3. Pone los enganches en los programas de IA que encuentre.
4. Deja una tarea programada que arranca el servicio al iniciar sesión,
   apuntando **a este mismo ejecutable**.
5. Lo arranca.

Nada de esto es destructivo: los enganches se fusionan con lo que ya hubiera y
se hace copia antes, y la tarea se sustituye si ya existía.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import instalador
from .config import Ajustes, ruta_config

#: Nombre de la tarea programada. El mismo que usa `instalar.ps1`, para que
#: instalar por un camino u otro no deje dos tareas peleándose por el teclado.
TAREA = "TecladoIA"


def _somos_un_exe() -> bool:
    """¿Nos está ejecutando PyInstaller desde un `.exe` empaquetado?"""
    return getattr(sys, "frozen", False)


def orden_de_arranque() -> str:
    """Cómo pedirle a este programa que arranque el servicio.

    Desde el `.exe` es él mismo; desde el código, `python -m tecladoia`.
    """
    if _somos_un_exe():
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{Path(sys.executable).resolve()}" -m tecladoia'


def hay_teclado_emparejado() -> bool:
    """¿Ve Windows algún AhaKey en su lista de dispositivos emparejados?"""
    if os.name != "nt":
        return False
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-PnpDevice -ErrorAction SilentlyContinue | "
             "Where-Object { $_.FriendlyName -like '*AhaKey*' }).Count"],
            capture_output=True, text=True, timeout=30,
        )
        return salida.stdout.strip() not in ("", "0")
    except Exception:  # noqa: BLE001 - sin PowerShell se sigue igual
        return False


def registrar_tarea(host: str = "") -> tuple[bool, str]:
    """Deja el servicio arrancando al iniciar sesión.

    Devuelve si se pudo y una explicación. No se aborta la instalación si
    falla: el programa sirve igual arrancándolo a mano, y decir en qué punto se
    quedó vale más que dejarlo a medias sin explicar nada.
    """
    if os.name != "nt":
        return False, "las tareas programadas son cosa de Windows"

    registro = Path(os.environ.get("APPDATA", Path.home())) / "TecladoIA" / "servicio.log"
    registro.parent.mkdir(parents=True, exist_ok=True)
    argumentos = "servicio" + (f" --host {host}" if host else "")
    # Se lanza minimizado y con la salida a un archivo. Sin eso, el servicio
    # arrancado por el programador de tareas es mudo: no hay consola donde
    # mirar, y averiguar por que no arranca se vuelve adivinar.
    # Ojo con las comillas: van tal cual, sin barras delante. `cmd` no entiende
    # `\"` como comilla escapada —eso es cosa de otros lenguajes—, y con ellas
    # el comando entero queda invalido. La tarea disparaba puntual y no
    # arrancaba nada, que desde fuera parece que el disparador no funciona.
    orden = (
        f'/c start /min "" cmd /c "{orden_de_arranque()} {argumentos} '
        f'>> "{registro}" 2>&1"'
    )
    guion = (
        f"$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '{orden}' "
        f"-WorkingDirectory '{Path.cwd()}';"
        "$d = New-ScheduledTaskTrigger -AtLogOn -User "
        "($env:USERDOMAIN + '\\' + $env:USERNAME);"
        "$d.Delay = 'PT20S';"
        # Segundo disparador: cada diez minutos, para siempre. No sustituye al
        # de inicio de sesion, lo respalda. Un disparador de sesion se puede
        # perder —arranques rapidos, sesiones que se restauran en vez de
        # abrirse— y entonces te encuentras el panel caido sin saber por que.
        #
        # Repetir es inofensivo porque el servicio se niega a arrancar si ya
        # hay otro vivo. Sin esa comprobacion esto crearia copias sin parar.
        "$r = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) "
        "-RepetitionInterval (New-TimeSpan -Minutes 10);"
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -StartWhenAvailable "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 "
        "-RestartInterval ([TimeSpan]::FromMinutes(1));"
        f"Register-ScheduledTask -TaskName '{TAREA}' -Action $a -Trigger @($d, $r) "
        "-Settings $s -Force | Out-Null"
    )
    try:
        hecho = subprocess.run(
            ["powershell", "-NoProfile", "-Command", guion],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as error:  # noqa: BLE001
        return False, str(error)
    if hecho.returncode != 0:
        return False, (hecho.stderr or "").strip().splitlines()[:1] and \
            (hecho.stderr or "").strip().splitlines()[0] or "no se pudo registrar"
    return True, (
        f"arrancará al iniciar sesión y se revisa cada diez minutos "
        f"(tarea «{TAREA}»)"
    )


def ejecutar(preguntar=input, escribir=print) -> int:
    """El asistente completo. Se le pueden pasar otras funciones para probarlo."""
    escribir("")
    escribir("  TecladoIA — instalación")
    escribir("  " + "-" * 24)
    escribir("")
    escribir("  La aplicación en español para el teclado AhaKey X1.")
    escribir("")

    ajustes = Ajustes.cargar()

    # --- 1. El teclado ------------------------------------------------
    escribir("==> Buscando el teclado")
    if hay_teclado_emparejado():
        escribir("    [ok] emparejado en este equipo")
    else:
        escribir("    [!]  no aparece ningún AhaKey emparejado.")
        escribir("         Empareja el teclado en Configuración > Bluetooth y")
        escribir("         vuelve a ejecutar esto. La instalación sigue igual.")

    # --- 2. La clave --------------------------------------------------
    escribir("")
    escribir("==> Clave del panel")
    escribir("    El panel decide qué puede hacer un agente sin preguntar, así")
    escribir("    que fuera de este equipo no se abre sin clave.")
    if ajustes.clave_panel:
        escribir(f"    Ya hay una puesta ({len(ajustes.clave_panel)} caracteres).")
        pregunta = "    Escribe otra, o Intro para dejar la que hay: "
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
    elif ajustes.clave_panel:
        escribir("    [ok] se deja la que ya había")
    else:
        escribir("    [!]  sin clave: el panel solo se abrirá en este equipo")

    # --- 3. Los enganches ---------------------------------------------
    escribir("")
    escribir("==> Poniendo los enganches en los programas de IA")
    try:
        resultado = instalador.instalar(None)
        for nombre, mensajes in resultado.items():
            escribir(f"    {nombre}")
            for mensaje in mensajes:
                escribir(f"      {mensaje}")
    except Exception as error:  # noqa: BLE001 - un enganche no tumba la instalación
        escribir(f"    [!]  no se pudieron poner del todo: {error}")

    # --- 4. Que arranque solo -----------------------------------------
    escribir("")
    escribir("==> Dejando el servicio arrancando con el equipo")
    hecho, detalle = registrar_tarea(ajustes.host_panel or "")
    escribir(("    [ok] " if hecho else "    [!]  ") + detalle)
    if not hecho:
        escribir(f"    Puedes arrancarlo a mano: {orden_de_arranque()} servicio")

    # --- 5. En marcha --------------------------------------------------
    escribir("")
    escribir("==> Listo")
    escribir(f"    Configuración en {ruta_config()}")
    puerto = ajustes.puerto_panel
    donde = ajustes.host_panel or "127.0.0.1"
    escribir(f"    Abre  http://{donde}:{puerto}")
    escribir("")
    escribir("    Si el teclado no aparece: enciéndelo y espera unos segundos.")
    escribir("    Y cierra la aplicación oficial de AhaKey si la tienes abierta,")
    escribir("    porque solo un programa puede hablar con el teclado a la vez.")
    escribir("")
    return 0


__all__ = ["ejecutar", "registrar_tarea", "hay_teclado_emparejado", "TAREA"]
