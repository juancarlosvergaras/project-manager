"""Órdenes de la Botonera: ``servicio``, ``estado``, ``aplicar``, ``luces``, ``escuchar``, ``tarea``."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from . import __version__, dispositivo, protocolo
from .config import NOMBRE, Ajustes, ruta_config, ruta_registro

_FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
TAREA = NOMBRE


def _salida_en_utf8() -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass


def hay_otro_servicio(ajustes: Ajustes) -> Optional[dict]:
    """Pregunta en el puerto del panel si ya hay una Botonera viva."""
    anfitriones = ["127.0.0.1"]
    if ajustes.host_panel not in ("", "127.0.0.1", "localhost", "0.0.0.0"):
        anfitriones.append(ajustes.host_panel)
    for anfitrion in anfitriones:
        for puerto in range(ajustes.puerto_panel, ajustes.puerto_panel + 5):
            try:
                with urllib.request.urlopen(f"http://{anfitrion}:{puerto}/api/salud", timeout=2) as r:
                    datos = json.loads(r.read().decode("utf-8"))
                if isinstance(datos, dict) and datos.get("app") == "botonera":
                    datos["puerto"] = puerto
                    return datos
            except Exception:  # noqa: BLE001
                continue
    return None


def orden_servicio(args: argparse.Namespace) -> int:
    ajustes = Ajustes.cargar()
    if args.host:
        ajustes.host_panel = args.host
    if args.puerto:
        ajustes.puerto_panel = args.puerto
    if not args.aunque_haya_otro:
        otro = hay_otro_servicio(ajustes)
        if otro is not None:
            print(f"Ya hay una {NOMBRE} en marcha en este equipo (puerto {otro['puerto']}).")
            return 3

    from .panel import PanelWeb
    from .servicio import Servicio

    async def ejecutar() -> int:
        servicio = Servicio(ajustes)
        panel = PanelWeb(servicio, ajustes)
        logging.getLogger("botonera").info("config: %s (%s)", ruta_config(), "existe" if ruta_config().exists() else "de fábrica")
        await servicio.arrancar()
        await panel.arrancar()
        if panel.puerto is None:
            await servicio.detener()
            return 1
        try:
            await asyncio.Event().wait()
        finally:
            await panel.detener()
            await servicio.detener()
        return 0

    try:
        return asyncio.run(ejecutar())
    except KeyboardInterrupt:
        return 0


def orden_estado(args: argparse.Namespace) -> int:
    ajustes = Ajustes.cargar()
    otro = hay_otro_servicio(ajustes)
    p = dispositivo.presencia()
    print(f"servicio: {'en marcha en el puerto ' + str(otro['puerto']) if otro else 'parado'}")
    print(f"teclado: {p.descripcion}" + (f" (serie {p.serie})" if p.serie else ""))
    print(f"configuración: {ruta_config()}")
    print(f"última grabación: {ajustes.ultima_escritura or 'nunca'}")
    for i, perfil in enumerate(ajustes.todos_los_perfiles()):
        print(f"  perfil {i + 1} «{perfil.nombre}»: {', '.join(perfil.teclas)} | perillas {perfil.perillas} | luz {perfil.luces_modo} {perfil.luces_color}")
    return 0


def orden_aplicar(args: argparse.Namespace) -> int:
    from .servicio import Servicio

    ajustes = Ajustes.cargar()
    servicio = Servicio(ajustes)
    servicio.estado.presencia = dispositivo.presencia()
    r = servicio.aplicar(args.perfil - 1 if args.perfil else None)
    print("grabado:" if r.get("escrito") else "no grabado:", r.get("mensajes", ""), r.get("aviso", "mensajes"))
    return 0 if r.get("escrito") else 2


def orden_luces(args: argparse.Namespace) -> int:
    from .servicio import Servicio

    ajustes = Ajustes.cargar()
    servicio = Servicio(ajustes)
    servicio.estado.presencia = dispositivo.presencia()
    r = servicio.poner_luces(args.perfil - 1, args.modo, args.color, solo_probar=args.probar)
    print(("probadas" if args.probar else "grabadas") if r.get("escrito") else "no grabadas:", r.get("luces") or r.get("aviso"))
    return 0 if r.get("escrito") else 2


def orden_escuchar(args: argparse.Namespace) -> int:
    from . import escucha

    print(f"escuchando el teclado {args.segundos:.0f} s… pulsa sus teclas y mueve las perillas.")
    for p in escucha.capturar(args.segundos, solo_el_teclado=not args.todo):
        print(f"{p['t']:6.2f}s  {p['origen']:9}  {p['tecla']}")
    return 0


def orden_de_arranque() -> str:
    """Con qué se lanza el servicio desde la tarea: pythonw si lo hay, sin consola."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    ejecutable = Path(sys.executable)
    sin_consola = ejecutable.with_name("pythonw.exe")
    if sin_consola.exists():
        ejecutable = sin_consola
    return f'"{ejecutable}" -m botonera'


def registrar_tarea(host: str = "", directorio: Path | None = None) -> tuple[bool, str]:
    """Deja el servicio arrancando al iniciar sesión y revisándose cada diez minutos."""
    if os.name != "nt":
        return False, "las tareas programadas son cosa de Windows"
    registro = ruta_registro()
    registro.parent.mkdir(parents=True, exist_ok=True)
    argumentos = "servicio" + (f" --host {host}" if host else "")
    # Las comillas van tal cual, sin barras: `cmd` no entiende `\"`.
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


def orden_tarea(args: argparse.Namespace) -> int:
    hecho, texto = quitar_tarea() if args.quitar else registrar_tarea(args.host, Path(args.directorio) if args.directorio else None)
    print(texto)
    return 0 if hecho else 1


def orden_asistente(args: argparse.Namespace) -> int:
    from . import asistente

    return asistente.ejecutar()


def construir_analizador() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="botonera", description=f"{NOMBRE} {__version__}: el teclado de 12 teclas, 3 perillas y luces, en español.")
    p.add_argument("--registro", default="info", choices=["info", "detalle", "aviso"], help="cuánto contar en el registro")
    sub = p.add_subparsers(dest="orden", required=True)

    s = sub.add_parser("servicio", help="arranca el servicio y el panel web")
    s.add_argument("--host", default="", help="dirección en la que escucha el panel (con clave si no es local)")
    s.add_argument("--puerto", type=int, default=0)
    s.add_argument("--aunque-haya-otro", action="store_true", help="arranca aunque ya haya un servicio")
    s.set_defaults(funcion=orden_servicio)

    e = sub.add_parser("estado", help="dice si el servicio está en marcha, por dónde va el teclado y qué tiene grabado")
    e.set_defaults(funcion=orden_estado)

    a = sub.add_parser("aplicar", help="graba en el teclado los tres perfiles (o uno) de la configuración")
    a.add_argument("--perfil", type=int, choices=range(1, protocolo.NUMERO_DE_PERFILES + 1), default=0)
    a.set_defaults(funcion=orden_aplicar)

    l = sub.add_parser("luces", help="pone las luces de un perfil: modo (0 apagado, 1 fijo, 2 reactivo, 3 onda, 4/5 arcoíris) y color")
    l.add_argument("perfil", type=int, choices=range(1, protocolo.NUMERO_DE_PERFILES + 1))
    l.add_argument("modo", type=int)
    l.add_argument("color", default="#ffffff", nargs="?")
    l.add_argument("--probar", action="store_true", help="mandarlas sin guardarlas")
    l.set_defaults(funcion=orden_luces)

    c = sub.add_parser("escuchar", help="enseña lo que manda el teclado al pulsarlo (la única forma de comprobar lo grabado)")
    c.add_argument("segundos", type=float, nargs="?", default=15)
    c.add_argument("--todo", action="store_true", help="también lo que venga de otros teclados")
    c.set_defaults(funcion=orden_escuchar)

    i = sub.add_parser("asistente", help="instalación guiada: clave, tarea programada y arranque")
    i.set_defaults(funcion=orden_asistente)

    r = sub.add_parser("tarea", help="crea (o quita) la tarea que arranca el servicio con Windows")
    r.add_argument("--host", default="")
    r.add_argument("--directorio", default="")
    r.add_argument("--quitar", action="store_true")
    r.set_defaults(funcion=orden_tarea)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    _salida_en_utf8()
    args = construir_analizador().parse_args(argv)
    nivel = {"info": logging.INFO, "detalle": logging.DEBUG, "aviso": logging.WARNING}[args.registro]
    logging.basicConfig(level=os.environ.get("BOTONERA_NIVEL") and logging.DEBUG or nivel, format=_FORMATO, datefmt="%H:%M:%S")
    try:
        return args.funcion(args)
    except (dispositivo.ErrorDispositivo, protocolo.ErrorProtocolo) as e:
        print(f"error: {e}")
        return 2
