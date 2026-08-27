"""Interfaz de línea de órdenes, en español."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import sys
from pathlib import Path
from typing import Any, Optional

from . import __version__, instalador, registro
from .config import Ajustes, directorio_base, ruta_config, ruta_socket
from .dispositivo import GestorTeclado
from .modelo import EfectoLuz, EstadoIA
from .panel import PanelWeb
from .registro import leer_bitacora
from .servidor import ServidorEnganches
from .transporte.base import ErrorTransporte, hay_bleak, normalizar_direccion

VERDE = "\033[32m"
ROJO = "\033[31m"
TENUE = "\033[2m"
FIN = "\033[0m"


class Salida:
    """Impresión con color opcional, apagable para lectores de pantalla."""

    def __init__(self, con_color: bool = True) -> None:
        self.con_color = con_color and sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    def _pintar(self, texto: str, codigo: str) -> str:
        return f"{codigo}{texto}{FIN}" if self.con_color else texto

    def titulo(self, texto: str) -> None:
        print(f"\n{self._pintar(texto, TENUE)}")

    def bien(self, texto: str) -> None:
        print(f"{self._pintar('[ok]', VERDE)} {texto}")

    def mal(self, texto: str) -> None:
        print(f"{self._pintar('[error]', ROJO)} {texto}", file=sys.stderr)

    def dato(self, etiqueta: str, valor: Any) -> None:
        print(f"  {etiqueta:<22} {valor}")

    def linea(self, texto: str = "") -> None:
        print(texto)


# --- utilidades ---------------------------------------------------------------

def _preguntar_al_servicio(peticion: dict[str, Any], ajustes: Ajustes) -> Optional[dict[str, Any]]:
    """Habla con un servicio ya en marcha, si lo hay."""
    carga = (json.dumps(peticion, ensure_ascii=False) + "\n").encode("utf-8")
    destinos: list[tuple[int, Any]] = []
    if os.name != "nt" and hasattr(socket, "AF_UNIX"):
        destinos.append((socket.AF_UNIX, str(ruta_socket())))
    for desplazamiento in range(3):
        destinos.append((socket.AF_INET, ("127.0.0.1", ajustes.puerto_hooks + desplazamiento)))
    for familia, direccion in destinos:
        try:
            with socket.socket(familia, socket.SOCK_STREAM) as cliente:
                cliente.settimeout(3)
                cliente.connect(direccion)
                cliente.sendall(carga)
                crudo = cliente.makefile("r", encoding="utf-8").readline()
        except (OSError, socket.timeout):
            continue
        try:
            datos = json.loads(crudo)
        except json.JSONDecodeError:
            continue
        if isinstance(datos, dict):
            return datos
    return None


def _palanca_legible(valor: Optional[int]) -> str:
    if valor is None:
        return "sin lectura (se pregunta siempre)"
    return "automático" if valor == 0 else f"manual (posición {valor})"


# --- órdenes ------------------------------------------------------------------

def orden_servicio(args, ajustes: Ajustes, salida: Salida) -> int:
    """Arranca el servicio: teclado, servidor de enganches y panel web."""

    if args.host:
        ajustes.host_panel = args.host
    if args.puerto_panel:
        ajustes.puerto_panel = args.puerto_panel

    async def ejecutar() -> int:
        gestor = GestorTeclado(ajustes)
        salida.titulo("Conectando con el teclado")
        try:
            await gestor.conectar()
            salida.bien(f"Teclado listo por {await gestor.descripcion_transporte()}")
        except ErrorTransporte as error:
            if args.sin_teclado:
                salida.linea(f"  No hay teclado a mano: {error}")
            else:
                salida.mal(str(error))
                salida.linea(
                    "Puedes seguir con «--sin-teclado» para trabajar en modo simulado."
                )
                return 1
        if not gestor.conectado and args.sin_teclado:
            from .transporte.simulado import TransporteSimulado

            gestor = GestorTeclado(ajustes, TransporteSimulado())
            await gestor.conectar()
            salida.bien("Modo simulado: hay teclado virtual, pero no hardware.")

        servidor = ServidorEnganches(gestor, ajustes)
        await servidor.arrancar(con_tcp=not args.sin_tcp)
        salida.titulo("Servicio en marcha")
        if servidor.ruta_socket:
            salida.dato("Socket", servidor.ruta_socket)
        if servidor.puerto:
            salida.dato("Puerto", servidor.puerto)

        panel: Optional[PanelWeb] = None
        if not args.sin_panel:
            panel = PanelWeb(gestor, servidor, ajustes)
            await panel.arrancar()
            if panel.url:
                salida.dato("Panel", panel.url)
                if ajustes.clave_panel:
                    salida.dato("Entrada", f"{panel.url}?clave={ajustes.clave_panel}")
            elif not panel.solo_local:
                salida.mal(
                    "El panel no se abrió: escuchar fuera de esta máquina exige clave. "
                    "Ponla con «tecladoia config --clave-panel generar»."
                )
                return 1

        salida.dato("Palanca", _palanca_legible(await gestor.palanca()))
        # Vigilantes de fondo. Sin el sondeo, mover la palanca o cambiar de
        # modo en el teclado no se entera nadie hasta el siguiente evento; y
        # sin el seguimiento de aplicaciones, el teclado no acompana a lo que
        # tienes delante, que es lo unico que sirve con programas que no avisan.
        vigilantes: list[asyncio.Task] = []
        vigilantes.append(asyncio.create_task(gestor.vigilar_estado()))
        if not args.sin_teclado:
            vigilantes.append(asyncio.create_task(gestor.mantener_conexion()))

        if getattr(ajustes, "seguir_aplicacion", True):
            from .enfoque import Vigilante, modo_para

            bucle = asyncio.get_running_loop()

            def al_cambiar_de_aplicacion(ventana) -> None:
                destino = modo_para(ventana, ajustes.aplicaciones)
                if destino is None:
                    return
                lectura = gestor.estado
                if lectura is not None and lectura.modo_trabajo == destino:
                    return
                # Un modo elegido con el boton del teclado manda sobre esto: no
                # se le devuelve a nadie al modo anterior por mirar otra ventana.
                if gestor.hay_tregua_de_modo():
                    return
                nombre = ajustes.modos[destino].nombre if destino < len(ajustes.modos) else destino + 1
                salida.linea(f"  {ventana.proceso} -> modo {nombre}")
                bucle.create_task(gestor.cambiar_modo_trabajo(destino))

            seguidor = Vigilante(al_cambiar_de_aplicacion)
            vigilantes.append(asyncio.create_task(seguidor.correr()))
            salida.dato("Sigue a", "la aplicacion activa")

        # La tecla del microfono manda una combinacion que solo entendemos
        # nosotros; aqui se traduce en «trae al frente el programa de este
        # modo, ponte en su cuadro de texto y abre el dictado». La segunda
        # pulsacion lo cierra, y con la palanca arriba manda lo dictado.
        escucha = None
        if getattr(ajustes, "dictado_asistido", True):
            import threading

            from .dictado import ATAJO_DICTADO, Dictado, EscuchaDictado, hay_soporte

            if hay_soporte():
                microfono = Dictado()

                def al_pulsar_microfono() -> None:
                    # El modo se lee de la ultima lectura del teclado, que el
                    # sondeo mantiene fresca. Con un modo viejo se enfocaria
                    # el programa equivocado, que es justo lo que pasaba.
                    lectura = gestor.estado
                    indice = lectura.modo_trabajo if lectura else None
                    modo = None
                    if indice is not None and 0 <= indice < len(ajustes.modos):
                        modo = ajustes.modos[indice]
                    palanca = lectura.palanca if lectura else None
                    hecho = microfono.alternar(
                        getattr(modo, "programa", "") if modo else "",
                        getattr(modo, "lanzar", "") if modo else "",
                        pinchar_el_cuadro=getattr(
                            ajustes, "pinchar_cuadro_al_dictar", True
                        ),
                        enviar_al_cerrar=(palanca == 0),
                    )
                    salida.linea(
                        "  microfono " + hecho["accion"] + " · " +
                        (hecho.get("programa") or "donde este el foco") +
                        (" · enviado" if hecho.get("enviado") else "")
                    )

                escucha = EscuchaDictado(al_pulsar_microfono)
                threading.Thread(target=escucha.correr, daemon=True).start()
                salida.dato("Microfono", "escuchando " + ATAJO_DICTADO)

        salida.linea("\nPulsa Ctrl+C para parar.")
        try:
            await servidor.servir_para_siempre()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            for tarea in vigilantes:
                tarea.cancel()
            if escucha is not None:
                escucha.parar()
            if panel is not None:
                await panel.detener()
            await servidor.detener()
            await gestor.desconectar()
        return 0

    try:
        return asyncio.run(ejecutar())
    except KeyboardInterrupt:
        salida.linea("\nServicio detenido.")
        return 0


def orden_estado(args, ajustes: Ajustes, salida: Salida) -> int:
    """Muestra el estado del teclado."""
    respuesta = _preguntar_al_servicio({"orden": "estado"}, ajustes)
    origen = "servicio en marcha"
    if respuesta is None:
        origen = "conexión directa"

        async def leer() -> dict[str, Any]:
            gestor = GestorTeclado(ajustes)
            try:
                await gestor.conectar()
            except ErrorTransporte as error:
                return {"error": str(error)}
            resumen = gestor.resumen()
            await gestor.desconectar()
            return resumen

        respuesta = asyncio.run(leer())

    if error := respuesta.get("error"):
        salida.mal(error)
        return 1

    salida.titulo(f"Estado del teclado ({origen})")
    salida.dato("Conexión", "conectado" if respuesta.get("conectado") else "sin conexión")
    salida.dato("Transporte", respuesta.get("transporte") or "—")
    salida.dato("Batería", f"{respuesta['bateria']} %" if respuesta.get("bateria") is not None else "—")
    salida.dato("Firmware", respuesta.get("firmware") or "—")
    salida.dato("Palanca", _palanca_legible(respuesta.get("palanca")))
    if respuesta.get("palanca_forzada"):
        salida.dato("", "(forzada desde el panel o la línea de órdenes)")
    salida.dato("Momento del agente", respuesta.get("estado_ia_etiqueta") or "—")
    if "agente_activo" in respuesta:
        salida.dato("Programa activo", respuesta.get("agente_activo") or "ninguno")
        segundos = respuesta.get("segundos_sin_eventos")
        salida.dato("Sin eventos desde", f"hace {segundos} s" if segundos is not None else "—")
    return 0


def orden_buscar(args, ajustes: Ajustes, salida: Salida) -> int:
    """Busca teclados AhaKey por Bluetooth."""
    if not hay_bleak():
        salida.mal("Falta «bleak». Instálalo con: pip install 'tecladoia[ble]'")
        return 1
    from .transporte.ble import buscar_teclados

    salida.titulo("Buscando teclados (unos segundos)")
    encontrados = asyncio.run(buscar_teclados(args.segundos))
    if not encontrados:
        salida.mal("No se encontró ningún teclado anunciándose.")
        salida.linea(
            "  Si en los ajustes de Bluetooth aparece como «Conectado», es lo esperado:\n"
            "  un teclado ya emparejado deja de anunciarse. Dale su dirección con\n"
            "  «tecladoia config --direccion XX:XX:XX:XX:XX:XX»."
        )
        return 1
    for direccion, nombre in encontrados:
        salida.bien(f"{nombre or 'sin nombre'} — {direccion}")
    if args.guardar:
        ajustes.direccion_dispositivo = encontrados[0][0]
        ajustes.guardar()
        salida.bien(f"Dirección guardada: {ajustes.direccion_dispositivo}")
    return 0


def orden_palanca(args, ajustes: Ajustes, salida: Salida) -> int:
    """Fija o libera la palanca virtual del servicio."""
    equivalencias = {"auto": 0, "automatico": 0, "automático": 0, "manual": 1}
    if args.modo in ("fisica", "física", "libre"):
        valor = None
    elif args.modo in equivalencias:
        valor = equivalencias[args.modo]
    else:
        salida.mal("Usa: auto, manual o fisica")
        return 2

    respuesta = _preguntar_al_servicio({"orden": "palanca", "valor": valor}, ajustes)
    if respuesta is None:
        salida.mal("No hay ningún servicio en marcha. Arráncalo con «tecladoia servicio».")
        return 1
    if valor is None:
        salida.bien("Manda la palanca física del teclado.")
    else:
        salida.bien(f"Palanca virtual fijada en {_palanca_legible(valor)}.")
    return 0


def orden_instalar(args, ajustes: Ajustes, salida: Salida) -> int:
    """Registra los enganches en los programas de IA."""
    try:
        resultado = instalador.instalar(args.agentes or None)
    except ValueError as error:
        salida.mal(str(error))
        return 2
    for nombre, mensajes in resultado.items():
        salida.titulo(nombre)
        for mensaje in mensajes:
            salida.linea(f"  {mensaje}")
    salida.linea("\nRecuerda dejar el servicio en marcha: tecladoia servicio")
    return 0


def orden_desinstalar(args, ajustes: Ajustes, salida: Salida) -> int:
    try:
        resultado = instalador.desinstalar(args.agentes or None)
    except ValueError as error:
        salida.mal(str(error))
        return 2
    for nombre, mensajes in resultado.items():
        salida.titulo(nombre)
        for mensaje in mensajes:
            salida.linea(f"  {mensaje}")
    return 0


def orden_agentes(args, ajustes: Ajustes, salida: Salida) -> int:
    """Lista los programas de IA y si tienen los enganches puestos."""
    salida.titulo("Programas de IA")
    for fila in instalador.revisar():
        marca = "sí" if fila["instalado"] else "no"
        salida.linea(
            f"  {fila['nombre']:<18} enganches: {marca:<3} "
            f"eventos: {fila['eventos']:<2} permisos: {fila['permisos']}"
        )
        salida.linea(f"  {'':<18} {fila['config']}")
    return 0


def orden_enganche(args, ajustes: Ajustes, salida: Salida) -> int:
    """Ejecuta el cliente de enganche (lo llaman los programas de IA)."""
    from .enganche import ejecutar

    extra = {"herramienta": args.herramienta, "comando": args.comando}
    return ejecutar(args.agente, args.evento, extra, ajustes)


def orden_teclas(args, ajustes: Ajustes, salida: Salida) -> int:
    """Programa una de las teclas del teclado."""

    if _preguntar_al_servicio({"orden": "estado"}, ajustes) is not None:
        salida.mal(
            "Hay un servicio en marcha con el teclado ocupado. "
            "Párale (Ctrl+C) antes de programar teclas."
        )
        return 1

    async def ejecutar() -> int:
        gestor = GestorTeclado(ajustes)
        try:
            await gestor.conectar()
        except ErrorTransporte as error:
            salida.mal(str(error))
            return 1
        hecho = await gestor.programar_tecla(
            args.modo, args.tecla, args.atajo or "", args.texto or ""
        )
        await gestor.desconectar()
        if hecho:
            salida.bien(
                f"Tecla {args.tecla + 1} del modo {args.modo} programada"
                + (f" con «{args.atajo}»" if args.atajo else "")
            )
            return 0
        salida.mal("No se pudo programar la tecla.")
        return 1

    return asyncio.run(ejecutar())


def orden_luz(args, ajustes: Ajustes, salida: Salida) -> int:
    """Cambia el efecto de la barra de luz."""
    try:
        efecto = EfectoLuz[args.efecto.upper()]
    except KeyError:
        salida.mal("Efectos disponibles: " + ", ".join(e.name.lower() for e in EfectoLuz))
        return 2

    # Si hay un servicio en marcha, es él quien tiene el enlace BLE: abrir una
    # segunda conexión chocaría con la suya.
    respuesta = _preguntar_al_servicio({"orden": "efecto", "valor": int(efecto)}, ajustes)
    if respuesta is not None:
        if respuesta.get("ok"):
            salida.bien(f"Efecto «{efecto.etiqueta}» aplicado por el servicio.")
            return 0
        salida.mal("El servicio no pudo aplicar el efecto; ¿está el teclado conectado?")
        return 1

    async def ejecutar() -> int:
        gestor = GestorTeclado(ajustes)
        try:
            await gestor.conectar()
        except ErrorTransporte as error:
            salida.mal(str(error))
            return 1
        hecho = await gestor.aplicar_efecto(efecto)
        await gestor.desconectar()
        salida.bien(f"Efecto «{efecto.etiqueta}» aplicado.") if hecho else salida.mal(
            "No se pudo aplicar el efecto."
        )
        return 0 if hecho else 1

    return asyncio.run(ejecutar())


def orden_bitacora(args, ajustes: Ajustes, salida: Salida) -> int:
    """Muestra las últimas decisiones de aprobación."""
    entradas = leer_bitacora(args.numero)
    if not entradas:
        salida.linea("La bitácora está vacía.")
        return 0
    salida.titulo(f"Últimas {len(entradas)} decisiones")
    for entrada in entradas:
        instante = str(entrada.get("instante", ""))[:19].replace("T", " ")
        accion = " · ".join(
            p for p in (entrada.get("herramienta"), entrada.get("comando")) if p
        )
        salida.linea(
            f"  {instante}  {entrada.get('agente', '?'):<8} "
            f"{entrada.get('decision', '?'):<9} {accion or '—'}"
        )
        if entrada.get("regla"):
            salida.linea(f"  {'':<21} regla: {entrada['regla']}")
    return 0


def orden_config(args, ajustes: Ajustes, salida: Salida) -> int:
    """Muestra la configuración y dónde vive."""
    if args.direccion is not None:
        ajustes.direccion_dispositivo = normalizar_direccion(args.direccion)
        ruta = ajustes.guardar()
        if ajustes.direccion_dispositivo:
            salida.bien(f"Teclado fijado en {ajustes.direccion_dispositivo} ({ruta})")
        else:
            salida.bien(f"Dirección borrada: se volverá a buscar el teclado ({ruta})")
        return 0
    if args.clave_panel is not None:
        valor = args.clave_panel.strip()
        if valor.lower() == "generar":
            valor = secrets.token_urlsafe(24)
        ajustes.clave_panel = valor
        ruta = ajustes.guardar()
        if valor:
            salida.bien(f"Clave del panel: {valor}")
            salida.linea(f"  Guardada en {ruta}. Entra con  ?clave={valor}")
        else:
            salida.bien(f"Clave borrada: el panel solo servirá en local ({ruta})")
        return 0
    if args.crear:
        ruta = ajustes.guardar()
        salida.bien(f"Configuración escrita en {ruta}")
        return 0
    salida.titulo("Configuración")
    salida.dato("Versión", f"{__version__} ({Path(__file__).resolve().parent})")
    salida.dato("Fichero", ruta_config())
    salida.dato("Carpeta", directorio_base())
    salida.dato("Modo de aprobación", ajustes.modo_aprobacion)
    salida.dato("Transporte", ajustes.transporte)
    salida.dato("Teclado fijado", ajustes.direccion_dispositivo or "no (se busca)")
    salida.dato("Puerto de enganches", ajustes.puerto_hooks)
    salida.dato("Puerto del panel", ajustes.puerto_panel)
    salida.dato("Panel escucha en", ajustes.host_panel)
    salida.dato("Clave del panel", ajustes.clave_panel or "sin clave (solo local)")
    salida.dato("Caché de la palanca", f"{ajustes.vigencia_cache_ms} ms")
    salida.dato("Reglas", len(ajustes.reglas))
    salida.titulo("Reglas")
    for regla in ajustes.reglas:
        salida.linea(f"  {regla.decision:<10} {regla.patron:<20} {regla.nota}")
    return 0


def orden_probar(args, ajustes: Ajustes, salida: Salida) -> int:
    """Recorre el flujo completo con un teclado simulado."""
    import logging

    from .transporte.simulado import TransporteSimulado

    # La demo se lee mejor sin el registro del servicio de por medio.
    logging.getLogger("tecladoia.servidor").setLevel(logging.WARNING)

    async def ejecutar() -> int:
        simulado = TransporteSimulado(palanca=1)
        gestor = GestorTeclado(ajustes, simulado)
        await gestor.conectar()
        servidor = ServidorEnganches(gestor, ajustes)

        casos = [
            ("codex", "CodexPermissionRequest", {"herramienta": "Bash", "comando": "ls -la"}),
            ("claude", "PermissionRequest", {"herramienta": "Bash", "comando": "rm -rf /"}),
            ("gemini", "GeminiBeforeTool", {"herramienta": "Shell", "comando": "git status"}),
        ]

        for posicion, titulo in ((1, "palanca en MANUAL"), (0, "palanca en AUTOMÁTICO")):
            simulado.mover_palanca(posicion)
            salida.titulo(f"Con la {titulo}")
            for agente_id, evento, contexto in casos:
                respuesta = await servidor.procesar(
                    json.dumps(
                        {
                            "orden": "evento",
                            "agente": agente_id,
                            "evento": evento,
                            "contexto": contexto,
                        }
                    )
                )
                salida.linea(
                    f"  {agente_id:<8} {contexto['comando']:<14} → "
                    f"{respuesta.get('decision')}  ({respuesta.get('explicacion')})"
                )
        await asyncio.sleep(0.05)
        salida.titulo("Estados reflejados en la barra de luz")
        salida.linea(f"  último estado enviado: {EstadoIA.desde_codigo(simulado.ultimo_estado or 0).etiqueta}")
        await gestor.desconectar()
        return 0

    return asyncio.run(ejecutar())


# --- entrada ------------------------------------------------------------------

def construir_analizador() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="tecladoia",
        description="Puente entre tu teclado AhaKey y los agentes de IA, en español.",
    )
    analizador.add_argument(
        "--version",
        action="version",
        version=f"TecladoIA {__version__} · {Path(__file__).resolve().parent}",
        help="versión instalada y desde dónde se está ejecutando",
    )
    analizador.add_argument("--sin-color", action="store_true", help="salida sin color ni adornos")
    analizador.add_argument(
        "--registro",
        default="info",
        choices=["critico", "error", "aviso", "info", "detalle"],
        help="nivel de detalle de los mensajes",
    )
    ordenes = analizador.add_subparsers(dest="orden", required=True, metavar="orden")

    servicio = ordenes.add_parser("servicio", help="arranca el servicio y el panel web")
    servicio.add_argument("--sin-panel", action="store_true", help="no abrir el panel web")
    servicio.add_argument("--sin-tcp", action="store_true", help="solo socket Unix")
    servicio.add_argument(
        "--sin-teclado", action="store_true", help="seguir en modo simulado si no hay teclado"
    )
    servicio.add_argument(
        "--host",
        default=None,
        help="interfaz del panel; fuera de 127.0.0.1 exige clave (p. ej. 0.0.0.0)",
    )
    servicio.add_argument("--puerto-panel", type=int, default=None, dest="puerto_panel")
    servicio.set_defaults(funcion=orden_servicio)

    estado = ordenes.add_parser("estado", help="muestra el estado del teclado")
    estado.set_defaults(funcion=orden_estado)

    buscar = ordenes.add_parser("buscar", help="busca teclados por Bluetooth")
    buscar.add_argument("--segundos", type=float, default=8.0)
    buscar.add_argument(
        "--guardar", action="store_true", help="fija el primer teclado encontrado"
    )
    buscar.set_defaults(funcion=orden_buscar)

    palanca = ordenes.add_parser("palanca", help="fija la palanca virtual: auto, manual o fisica")
    palanca.add_argument("modo", help="auto | manual | fisica")
    palanca.set_defaults(funcion=orden_palanca)

    instalar = ordenes.add_parser("instalar", help="pone los enganches en los programas de IA")
    instalar.add_argument("agentes", nargs="*", help="claude, codex, cursor, kimi, gemini")
    instalar.set_defaults(funcion=orden_instalar)

    desinstalar = ordenes.add_parser("desinstalar", help="quita los enganches")
    desinstalar.add_argument("agentes", nargs="*")
    desinstalar.set_defaults(funcion=orden_desinstalar)

    listar = ordenes.add_parser("agentes", help="lista los programas de IA admitidos")
    listar.set_defaults(funcion=orden_agentes)

    enganche = ordenes.add_parser("enganche", help="cliente que llaman los programas de IA")
    enganche.add_argument("agente")
    enganche.add_argument("evento")
    enganche.add_argument("--herramienta", default=None)
    enganche.add_argument("--comando", default=None)
    enganche.set_defaults(funcion=orden_enganche)

    teclas = ordenes.add_parser("tecla", help="programa una tecla del teclado")
    teclas.add_argument("modo", type=int, choices=[0, 1, 2])
    teclas.add_argument("tecla", type=int, choices=[0, 1, 2, 3])
    teclas.add_argument("--atajo", help="por ejemplo: ctrl+may+p")
    teclas.add_argument("--texto", help="etiqueta que se ve en la pantalla del teclado")
    teclas.set_defaults(funcion=orden_teclas)

    luz = ordenes.add_parser("luz", help="cambia el efecto de la barra de luz")
    luz.add_argument("efecto")
    luz.set_defaults(funcion=orden_luz)

    bitacora = ordenes.add_parser("bitacora", help="últimas decisiones de aprobación")
    bitacora.add_argument("-n", "--numero", type=int, default=20)
    bitacora.set_defaults(funcion=orden_bitacora)

    config = ordenes.add_parser("config", help="muestra la configuración")
    config.add_argument("--crear", action="store_true", help="escribe el fichero de configuración")
    config.add_argument(
        "--clave-panel",
        default=None,
        dest="clave_panel",
        metavar="CLAVE",
        help="clave del panel; «generar» crea una al azar y vacío la borra",
    )
    config.add_argument(
        "--direccion",
        default=None,
        metavar="XX:XX:XX:XX:XX:XX",
        help=(
            "fija la dirección Bluetooth del teclado; admite el identificador de "
            "instancia de Windows tal cual (cadena vacía para olvidarla)"
        ),
    )
    config.set_defaults(funcion=orden_config)

    probar = ordenes.add_parser("probar", help="prueba el flujo completo sin teclado")
    probar.set_defaults(funcion=orden_probar)

    return analizador


def main(argumentos: Optional[list[str]] = None) -> int:
    analizador = construir_analizador()
    args = analizador.parse_args(argumentos)
    ajustes = Ajustes.cargar()
    registro.configurar(args.registro)
    salida = Salida(con_color=not (args.sin_color or ajustes.es_accesible()))
    try:
        return args.funcion(args, ajustes, salida)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Alguien cortó la salida con «| head» o similar; no es un fallo nuestro.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
