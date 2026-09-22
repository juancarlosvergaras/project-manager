"""Órdenes de OneKey: ``servicio``, ``estado``, ``asistente``, ``tarea``."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from . import __version__
from .config import NOMBRE, Ajustes, ruta_config

_FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def _salida_en_utf8() -> None:
    # Bajo pythonw (o el ejecutable sin consola) no hay consola y sys.stdout es
    # None: cualquier print reventaría el servicio nada más arrancar.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass


def hay_otro_servicio(ajustes: Ajustes) -> Optional[dict]:
    """Pregunta en el puerto del panel si ya hay un OneKey vivo."""
    anfitriones = ["127.0.0.1"]
    if ajustes.host_panel not in ("", "127.0.0.1", "localhost", "0.0.0.0"):
        anfitriones.append(ajustes.host_panel)
    for anfitrion in anfitriones:
        for puerto in range(ajustes.puerto_panel, ajustes.puerto_panel + 5):
            try:
                with urllib.request.urlopen(f"http://{anfitrion}:{puerto}/api/salud", timeout=2) as r:
                    datos = json.loads(r.read().decode("utf-8"))
                if isinstance(datos, dict) and datos.get("app") == "onekey":
                    datos["puerto"] = puerto
                    return datos
            except Exception:  # noqa: BLE001
                continue
    return None


def orden_servicio(args: argparse.Namespace) -> int:
    from tecladoia.registro import a_archivo

    from .config import ruta_registro

    a_archivo(ruta_registro())  # el registro lo escribe el servicio, no cmd
    ajustes = Ajustes.cargar()
    if args.host:
        ajustes.host_panel = args.host
    if args.puerto:
        ajustes.puerto_panel = args.puerto
    if not args.aunque_haya_otro:
        otro = hay_otro_servicio(ajustes)
        if otro is not None:
            print(f"Ya hay un {NOMBRE} en marcha en este equipo (puerto {otro['puerto']}).")
            return 3

    from .panel import PanelWeb
    from .servicio import Servicio

    async def ejecutar() -> int:
        servicio = Servicio(ajustes)
        panel = PanelWeb(servicio, ajustes)
        logging.getLogger("onekey").info(
            "config: %s (%s)", ruta_config(), "existe" if ruta_config().exists() else "de fábrica"
        )
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
    from minimic import boton

    ajustes = Ajustes.cargar()
    otro = hay_otro_servicio(ajustes)
    b = boton.buscar(ajustes.boton_bluetooth)
    print(f"servicio: {'en marcha en el puerto ' + str(otro['puerto']) if otro else 'parado'}")
    print(f"botón «{ajustes.boton_bluetooth}»: {b.descripcion if b else 'no está (¿encendido y emparejado?)'}")
    print(f"configuración: {ruta_config()}")
    return 0


def orden_tarea(args: argparse.Namespace) -> int:
    from . import asistente

    if args.quitar:
        hecho, texto = asistente.quitar_tarea()
    else:
        hecho, texto = asistente.registrar_tarea(args.host, Path(args.directorio) if args.directorio else None)
    print(texto)
    return 0 if hecho else 1


def orden_asistente(args: argparse.Namespace) -> int:
    from . import asistente

    return asistente.ejecutar()


def construir_analizador() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="onekey", description=f"{NOMBRE} {__version__}: el botón Bluetooth de una tecla con micrófono, en español.")
    p.add_argument("--registro", default="info", choices=["info", "detalle", "aviso"], help="cuánto contar en el registro")
    sub = p.add_subparsers(dest="orden", required=True)

    s = sub.add_parser("servicio", help="arranca el servicio y el panel web")
    s.add_argument("--host", default="", help="dirección en la que escucha el panel (con clave si no es local)")
    s.add_argument("--puerto", type=int, default=0)
    s.add_argument("--aunque-haya-otro", action="store_true", help="arranca aunque ya haya un servicio")
    s.set_defaults(funcion=orden_servicio)

    e = sub.add_parser("estado", help="dice si el servicio está en marcha y si ve el botón")
    e.set_defaults(funcion=orden_estado)

    a = sub.add_parser("asistente", help="instalación guiada: tarea programada y arranque")
    a.set_defaults(funcion=orden_asistente)

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
    logging.basicConfig(level=os.environ.get("ONEKEY_NIVEL") and logging.DEBUG or nivel, format=_FORMATO, datefmt="%H:%M:%S")
    return args.funcion(args)
