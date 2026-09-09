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
    # Se prefiere pythonw.exe, que es el mismo Python sin consola. El servicio
    # se moria con un «^C» en el registro cada pocas horas: algo le mandaba una
    # interrupcion a la ventana de consola donde vivia, ahi minimizada
    # esperando a que alguien la cerrara sin querer. Sin consola no hay a quien
    # interrumpir. La salida sigue yendo al registro, porque la redireccion la
    # hace `cmd` y no la consola.
    interprete = Path(sys.executable).resolve()
    sin_consola = interprete.with_name("pythonw.exe")
    if os.name == "nt" and sin_consola.is_file():
        interprete = sin_consola
    return f'"{interprete}" -m tecladoia'


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


def ejecutable_y_argumentos(argumentos: str = "") -> tuple[str, str]:
    """Qué programa lanza la tarea y con qué argumentos, **sin consola**.

    Antes la tarea lanzaba `cmd /c start /min "" cmd /c "pythonw … >> registro"`
    para tener registro. Cada disparador de diez minutos asomaba una consola
    minimizada en la barra de tareas —cuatro teclados, una ventana cada dos
    minutos y medio—, aunque el servicio se retirara al ver que ya había otro.
    Ahora la tarea ejecuta `pythonw.exe` (o el propio .exe) directamente y el
    servicio escribe su registro él mismo (`tecladoia.registro.a_archivo`).
    """
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), argumentos.strip()
    interprete = Path(sys.executable).resolve()
    sin_consola = interprete.with_name("pythonw.exe")
    if os.name == "nt" and sin_consola.is_file():
        interprete = sin_consola
    return str(interprete), f"-m {'tecladoia'} {argumentos}".strip()


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
    # Sin cmd ni consola: pythonw directamente. El registro lo escribe el
    # propio servicio en %APPDATA%\TecladoIA\servicio.log (registro.a_archivo).
    ejecutable, arg_tarea = ejecutable_y_argumentos(argumentos)
    guion = (
        f"$a = New-ScheduledTaskAction -Execute '{ejecutable}' -Argument '{arg_tarea}' "
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


def acceso_directo_en_el_escritorio(url: str) -> str:
    """Deja «TecladoIA.url» en el escritorio apuntando al panel local. Devuelve la ruta o «»."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(0, 0x10, 0, 0, buf)  # CSIDL_DESKTOPDIRECTORY
        escritorio = Path(buf.value) if buf.value else Path.home() / "Desktop"
        destino = escritorio / "TecladoIA.url"
        destino.write_text(f"[InternetShortcut]\nURL={url}\nIconIndex=0\n", encoding="utf-8")
        return str(destino)
    except Exception:  # noqa: BLE001 - un escritorio raro no debe tumbar la instalación
        return ""


def abrir_en_el_navegador(url: str) -> bool:
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001
        return False


def detener_servicios_anteriores() -> int:
    """Para cualquier TecladoIA que quede vivo. Devuelve cuántos paró.

    Al reinstalar encima, el servicio viejo seguía en marcha y el nuevo, al
    arrancar, veía que «ya hay otro» y se retiraba: uno se quedaba con el
    código de antes creyendo que había actualizado.
    """
    if os.name != "nt":
        return 0
    guion = (
        "$mio = $PID; Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -like 'python*' -or $_.Name -like 'TecladoIA*') -and $_.ProcessId -ne $mio "
        "-and $_.CommandLine -like '*tecladoia*servicio*' } | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    try:
        hecho = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True,
                               timeout=40, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:  # noqa: BLE001
        return 0
    subprocess.run(["schtasks", "/End", "/TN", TAREA], capture_output=True, text=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return len([l for l in hecho.stdout.split() if l.strip().isdigit()])


def arrancar_ahora(host: str = "") -> bool:
    """Arranca el servicio ya, sin esperar al programador de tareas ni abrir consola."""
    if os.name != "nt":
        return False
    ejecutable, argumentos = ejecutable_y_argumentos("servicio" + (f" --host {host}" if host else ""))
    try:
        subprocess.Popen(
            [ejecutable, *argumentos.split()] if argumentos else [ejecutable],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=str(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def esperar_al_servicio(puerto: int, plazo_s: float = 30.0) -> str:
    """La versión del servicio que contesta en /api/estado (en local no pide clave), o «»."""
    import json
    import time
    import urllib.request

    limite = time.monotonic() + plazo_s
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/estado", timeout=2) as r:
                datos = json.loads(r.read().decode("utf-8"))
            if isinstance(datos, dict) and "estado" in datos:
                return str(datos.get("servicio", {}).get("version") or "en marcha")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return ""


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
    escribir("==> Parando lo que hubiera de antes")
    parados = detener_servicios_anteriores()
    escribir(f"    [ok] {parados} servicio(s) anterior(es) parado(s)" if parados else "    [ok] no había ninguno")

    escribir("")
    escribir("==> Dejando el servicio arrancando con el equipo")
    host_publico = ajustes.host_panel if ajustes.host_panel not in ("", "127.0.0.1", "localhost") else ""
    hecho, detalle = registrar_tarea(host_publico)
    escribir(("    [ok] " if hecho else "    [!]  ") + detalle)
    if arrancar_ahora(host_publico):
        escribir("    … arrancando el servicio")
        version = esperar_al_servicio(ajustes.puerto_panel)
        if version:
            escribir(f"    [ok] el servicio contesta: TecladoIA {version}")
        else:
            escribir("    [!]  el servicio no contesta en 30 s; mira %APPDATA%\\TecladoIA\\servicio.log")
    elif hecho:
        subprocess.run(["schtasks", "/Run", "/TN", TAREA], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        escribir("    [ok] se le pidió arrancar a la tarea programada")
    else:
        escribir(f"    Puedes arrancarlo a mano: {orden_de_arranque()} servicio")

    # --- 5. En marcha --------------------------------------------------
    escribir("")
    escribir("==> Listo")
    escribir(f"    Configuración en {ruta_config()}")
    puerto = ajustes.puerto_panel
    # El panel de este equipo es el camino principal: no depende de Internet
    # ni de ningún otro ordenador. Se deja a mano y se abre.
    local = f"http://127.0.0.1:{puerto}/"
    acceso = acceso_directo_en_el_escritorio(local)
    if acceso:
        escribir(f"    [ok] acceso directo al panel en el escritorio: {acceso}")
    escribir(f"    El panel de este equipo: {local}  (sin clave desde aquí)")
    if ajustes.host_panel and ajustes.host_panel != "127.0.0.1":
        escribir(f"    Y desde fuera, con clave: http://{ajustes.host_panel}:{puerto}")
    if hecho and abrir_en_el_navegador(local):
        escribir("    [ok] abierto en el navegador")
    escribir("")
    escribir("    Si el teclado no aparece: enciéndelo y espera unos segundos.")
    escribir("    Y cierra la aplicación oficial de AhaKey si la tienes abierta,")
    escribir("    porque solo un programa puede hablar con el teclado a la vez.")
    escribir("")
    return 0


__all__ = ["ejecutar", "registrar_tarea", "hay_teclado_emparejado", "TAREA"]
