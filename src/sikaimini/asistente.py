"""Que SikaiMini arranque con Windows: la tarea programada.

Misma receta que TecladoIA y MiniMic, con su nombre, su registro y su orden. Dos
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

TAREA = NOMBRE  # «SikaiMini»


def orden_de_arranque() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    interprete = Path(sys.executable).resolve()
    sin_consola = interprete.with_name("pythonw.exe")
    if os.name == "nt" and sin_consola.is_file():
        interprete = sin_consola
    return f'"{interprete}" -m sikaimini'


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


def grabar_el_teclado(ajustes: Ajustes, escribir=print) -> None:
    """Deja el teclado como se quiere ahí mismo, sin esperar al servicio."""
    from . import dispositivo, protocolo
    from .protocolo import Atajo

    try:
        teclado = dispositivo.Teclado()
        mapa = teclado.leer_capa(0)
        cambios = 0
        for indice, texto in enumerate(ajustes.teclas):
            atajo = Atajo.desde_texto(texto)
            if mapa.teclas.get(indice) != atajo:
                teclado.escribir_tecla(0, indice, atajo)
                cambios += 1
        if teclado.ajustes().modo_microfono != ajustes.modo_microfono:
            teclado.modo_microfono(ajustes.modo_microfono)
            cambios += 1
        piezas = ", ".join(f"{n}: {t}" for n, t in zip(protocolo.NOMBRES_DE_LAS_PIEZAS, ajustes.teclas))
        escribir(f"    [ok] teclado grabado ({cambios} cambio(s)): {piezas}")
    except Exception as error:  # noqa: BLE001 - el servicio lo reintenta al arrancar
        escribir(f"    [!]  no se pudo grabar ahora ({error}); el servicio lo hará al arrancar")


def detener_servicios_anteriores() -> int:
    """Para cualquier sikaimini servicio que quede vivo. Devuelve cuántos paró.

    Al reinstalar encima, el servicio viejo seguía en marcha y el nuevo, al
    arrancar, veía que «ya hay otro» y se retiraba: uno se quedaba con el
    código de antes creyendo que había actualizado.
    """
    if os.name != "nt":
        return 0
    guion = (
        "$mio = $PID; Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -like 'python*' -or $_.Name -like 'sikaimini*') -and $_.ProcessId -ne $mio "
        "-and $_.CommandLine -like '*sikaimini*servicio*' } | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    try:
        hecho = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True, timeout=40)
    except Exception:  # noqa: BLE001
        return 0
    subprocess.run(["schtasks", "/End", "/TN", TAREA], capture_output=True, text=True)
    return len([l for l in hecho.stdout.split() if l.strip().isdigit()])


def arrancar_ahora(host: str = "") -> bool:
    """Arranca el servicio ya, sin esperar al programador de tareas.

    Pedírselo a la tarea (`schtasks /Run`) devuelve «correcto» al instante y
    Windows lo deja en cola: a veces arranca en dos segundos y a veces en
    medio minuto, y mientras tanto el panel recién abierto no tiene a quién
    preguntar. Se lanza aquí mismo, sin ventana, con la salida al registro;
    la tarea queda para los siguientes arranques (si encuentra este vivo, se
    retira sola).
    """
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
    """Devuelve la versión que contesta en /api/salud, o «» si no llega a tiempo."""
    import json
    import time
    import urllib.request

    limite = time.monotonic() + plazo_s
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=2) as r:
                datos = json.loads(r.read().decode("utf-8"))
            if isinstance(datos, dict) and datos.get("app") == "sikaimini":
                return str(datos.get("version") or "?")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return ""


def ejecutar(preguntar=input, escribir=print) -> int:
    """La instalación guiada: lo que hace `SikaiMini.exe` al abrirse sin argumentos."""
    from . import dispositivo

    escribir("")
    escribir(f"  {NOMBRE} — instalación")
    escribir("  " + "-" * 22)
    escribir("")
    escribir("  La aplicación en español para el mini teclado SiKai: tres teclas, perilla y micrófono.")
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
                grabar_el_teclado(ajustes, escribir)
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
    escribir("==> Dónde escucha el panel")
    from .panel import direcciones_locales

    tailscale = [d for d in direcciones_locales() if d.startswith("100.")]
    if not ajustes.clave_panel:
        escribir("    Sin clave, solo en este equipo (http://127.0.0.1:%d)." % ajustes.puerto_panel)
    elif not tailscale:
        escribir("    No veo Tailscale en este equipo; el panel queda en http://127.0.0.1:%d." % ajustes.puerto_panel)
        escribir("    Con Tailscale instalado, sikaimini.proyectoia.org pasaría a este equipo.")
    else:
        direccion = tailscale[0]
        escribir(f"    Este equipo tiene Tailscale en {direccion}. Publicando el panel ahí,")
        escribir("    sikaimini.proyectoia.org pasa a este equipo cuando tenga el teclado.")
        try:
            respuesta = (preguntar(f"    ¿Publicarlo en {direccion}? [S/n]: ") or "s").strip().lower()
        except (EOFError, KeyboardInterrupt):
            respuesta = "s"
        if respuesta.startswith("s"):
            ajustes.host_panel = direccion
            ajustes.guardar()
            escribir(f"    [ok] el panel escuchará en http://{direccion}:{ajustes.puerto_panel}")
            escribir("         Si Windows pregunta si permite a SikaiMini en la red, di que sí.")
        else:
            ajustes.host_panel = "127.0.0.1"
            ajustes.guardar()

    escribir("")
    escribir("==> Parando lo que hubiera de antes")
    parados = detener_servicios_anteriores()
    escribir(f"    [ok] {parados} servicio(s) anterior(es) parado(s)" if parados else "    [ok] no había ninguno")

    escribir("")
    escribir("==> Dejando el servicio arrancando con el equipo")
    hecho, detalle = registrar_tarea(ajustes.host_panel if ajustes.host_panel != "127.0.0.1" else "")
    escribir(("    [ok] " if hecho else "    [!]  ") + detalle)
    host_publico = ajustes.host_panel if ajustes.host_panel != "127.0.0.1" else ""
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
    # El panel de este equipo es el camino principal: no depende de Internet
    # ni de ningún otro ordenador. Se deja a mano y se abre.
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
    escribir("    La tecla del micrófono abre el dictado en el programa que elijas en el panel.")
    escribir("    Conecta el teclado por cable una vez para que se le graben las teclas y la perilla.")
    escribir("")
    return 0
