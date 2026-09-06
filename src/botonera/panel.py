"""El panel web de la Botonera: HTTP a mano sobre asyncio, como en las otras tres.

Mismas reglas de la casa: fuera de la máquina local exige clave (cabecera
``X-Botonera-Clave``, ``Authorization: Bearer``, cookie ``botonera`` o
``?clave=`` una sola vez, que se convierte en cookie); comparación de tiempo
constante; estáticos sin salir de su carpeta; canal de sucesos (SSE) con
latido cada veinte segundos; y desde el propio equipo no se pide clave.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import secrets
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from sikaimini.protocolo import CONSUMO

from . import __version__, dispositivo, protocolo
from .config import Ajustes, ruta_registro
from .servicio import Servicio

registro = logging.getLogger("botonera.panel")

CARPETA_WEB = Path(__file__).resolve().parent / "web"
LATIDO_S = 20.0
_FIN = "\r\n"

#: Ajustes que se pueden cambiar desde la web, con su tipo.
_CAMPOS_AJUSTES = {"clave_panel": str, "host_panel": str, "escribir_al_conectar": bool}

#: Combinaciones que abren el dictado de los otros servicios de la casa.
ATAJOS_DE_DICTADO = [
    {"id": "tecladoia", "nombre": "Dictado de TecladoIA (AhaKey)", "accion": "ctrl-mayus-alt-f13"},
    {"id": "minimic", "nombre": "Dictado de MiniMic", "accion": "ctrl-mayus-alt-f14"},
    {"id": "sikaimini", "nombre": "Dictado de SikaiMini", "accion": "ctrl-mayus-alt-f15"},
]


def _cola_del_registro(cuantas: int = 120) -> list[str]:
    try:
        with open(ruta_registro(), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 64_000))
            texto = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return texto.splitlines()[-cuantas:]


def _nombre_del_equipo() -> str:
    import socket
    try:
        return socket.gethostname()
    except OSError:
        return ""


def direcciones_locales() -> list[str]:
    """Las IP de este equipo en las que se puede publicar el panel (Tailscale incluida)."""
    import socket
    vistas: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in vistas and not ip.startswith("127."):
                vistas.append(ip)
    except OSError:
        pass
    vistas.sort(key=lambda ip: (not ip.startswith("100."), ip))
    return vistas


def _suceso(tipo: str, carga: str, identificador: Optional[int] = None) -> bytes:
    cabeza = f"id: {identificador}\n" if identificador is not None else ""
    return f"{cabeza}event: {tipo}\ndata: {carga}\n\n".encode("utf-8")


class PanelWeb:
    def __init__(self, servicio: Servicio, ajustes: Optional[Ajustes] = None) -> None:
        self.servicio = servicio
        self.ajustes = ajustes or servicio.ajustes
        self.puerto: Optional[int] = None
        self._http: Optional[asyncio.AbstractServer] = None

    @property
    def solo_local(self) -> bool:
        return self.ajustes.host_panel in ("127.0.0.1", "::1", "localhost")

    @property
    def url(self) -> str:
        if not self.puerto:
            return ""
        anfitrion = "127.0.0.1" if self.ajustes.host_panel == "0.0.0.0" else self.ajustes.host_panel
        return f"http://{anfitrion}:{self.puerto}/"

    def _donde_escuchar(self) -> list[str]:
        host = self.ajustes.host_panel
        if host in ("", "127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return [host or "127.0.0.1"]
        return ["127.0.0.1", host]

    async def arrancar(self) -> None:
        if not self.solo_local and not self.ajustes.clave_panel:
            registro.error("El panel iba a escuchar en %s sin clave y no se ha abierto.", self.ajustes.host_panel)
            return
        base = self.ajustes.puerto_panel
        for intento in range(5):
            try:
                self._http = await asyncio.start_server(self._atender, self._donde_escuchar(), base + intento)
            except OSError:
                continue
            self.puerto = base + intento
            registro.info("Panel disponible en %s%s", self.url, "" if self.solo_local else " (con clave)")
            return
        registro.error("No se pudo abrir el panel entre los puertos %s y %s", base, base + 4)

    async def detener(self) -> None:
        if self._http is None:
            return
        self._http.close()
        with contextlib.suppress(Exception):
            await self._http.wait_closed()
        self._http = None

    # --- HTTP ---------------------------------------------------------------

    async def _atender(self, lector: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        try:
            peticion = await asyncio.wait_for(lector.readline(), timeout=5)
            if not peticion:
                return
            metodo, destino, _ = peticion.decode("latin-1").split(" ", 2)
            cabeceras: dict[str, str] = {}
            while True:
                linea = await asyncio.wait_for(lector.readline(), timeout=5)
                if linea in (b"\r\n", b"\n", b""):
                    break
                nombre, _, valor = linea.decode("latin-1").partition(":")
                cabeceras[nombre.strip().lower()] = valor.strip()
            longitud = int(cabeceras.get("content-length") or 0)
            cuerpo = await lector.readexactly(longitud) if longitud else b""
            partes = urlparse(destino)
            consulta = parse_qs(partes.query)
            extras: list[str] = []

            if partes.path == "/api/salud":
                # Sin clave a propósito: es lo que pregunta el siguiente arranque
                # para no abrir dos servicios sobre el mismo teclado.
                estado, tipo, datos = self._json_ok({
                    "app": "botonera", "version": __version__,
                    "teclado": self.servicio.estado.presencia.conectado,
                    "equipo": _nombre_del_equipo(),
                })
            elif not self._autorizado(cabeceras, consulta, self._es_local(escritor)):
                estado, tipo, datos = self._sin_permiso()
            elif consulta.get("clave"):
                extras.append(f"Set-Cookie: botonera={self.ajustes.clave_panel}; Path=/; HttpOnly; SameSite=Strict")
                extras.append(f"Location: {partes.path or '/'}")
                estado, tipo, datos = "303 See Other", "text/plain; charset=utf-8", b""
            elif partes.path == "/api/sucesos" and metodo == "GET":
                await self._transmitir_sucesos(escritor)
                return
            else:
                estado, tipo, datos = await self._responder(metodo, partes.path, cuerpo)
            escritor.write(self._envolver(estado, tipo, datos, extras))
            await escritor.drain()
        except (asyncio.TimeoutError, ValueError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            escritor.close()
            with contextlib.suppress(Exception):
                await escritor.wait_closed()

    #: Desde el propio equipo no se pide clave. Las pruebas lo apagan.
    confiar_en_local = True

    @staticmethod
    def _es_local(escritor: asyncio.StreamWriter) -> bool:
        try:
            par = escritor.get_extra_info("peername")
        except Exception:  # noqa: BLE001
            return False
        return bool(par) and par[0] in ("127.0.0.1", "::1")

    def _autorizado(self, cabeceras: dict[str, str], consulta: dict[str, list[str]], es_local: bool = False) -> bool:
        esperada = self.ajustes.clave_panel
        if not esperada:
            return True
        if es_local and self.confiar_en_local:
            return True
        candidatas: list[str] = []
        autorizacion = cabeceras.get("authorization", "")
        if autorizacion.lower().startswith("bearer "):
            candidatas.append(autorizacion[7:].strip())
        if cabecera := cabeceras.get("x-botonera-clave"):
            candidatas.append(cabecera.strip())
        for trozo in cabeceras.get("cookie", "").split(";"):
            nombre, _, valor = trozo.strip().partition("=")
            if nombre == "botonera":
                candidatas.append(valor.strip())
        candidatas.extend(consulta.get("clave", []))
        return any(secrets.compare_digest(c, esperada) for c in candidatas)

    @staticmethod
    def _sin_permiso() -> tuple[str, str, bytes]:
        pagina = (CARPETA_WEB / "entrar.html").read_text(encoding="utf-8")
        return "401 Unauthorized", "text/html; charset=utf-8", pagina.encode("utf-8")

    @staticmethod
    def _envolver(estado: str, tipo: str, cuerpo: bytes, extras: Optional[list[str]] = None) -> bytes:
        cabeceras = [
            f"HTTP/1.1 {estado}", f"Content-Type: {tipo}", f"Content-Length: {len(cuerpo)}",
            "Cache-Control: no-store", "X-Content-Type-Options: nosniff",
            "Referrer-Policy: no-referrer", "Connection: close",
        ]
        cabeceras.extend(extras or [])
        return (_FIN.join(cabeceras) + _FIN + _FIN).encode("latin-1") + cuerpo

    # --- canal de sucesos --------------------------------------------------------

    async def _transmitir_sucesos(self, escritor: asyncio.StreamWriter) -> None:
        escritor.write((
            "HTTP/1.1 200 OK" + _FIN + "Content-Type: text/event-stream; charset=utf-8" + _FIN
            + "Cache-Control: no-store" + _FIN + "Connection: keep-alive" + _FIN
            + "X-Accel-Buffering: no" + _FIN + _FIN
        ).encode("latin-1"))
        await escritor.drain()
        cola = self.servicio.bus.suscribir()
        try:
            escritor.write(_suceso("bienvenida", json.dumps(self.servicio.resumen(), ensure_ascii=False, default=str)))
            await escritor.drain()
            while True:
                try:
                    suceso = await asyncio.wait_for(cola.get(), timeout=LATIDO_S)
                except asyncio.TimeoutError:
                    escritor.write(b": latido\n\n")
                    await escritor.drain()
                    continue
                carga = json.dumps(suceso["datos"], ensure_ascii=False, default=str)
                escritor.write(_suceso(suceso["tipo"], carga, suceso["id"]))
                await escritor.drain()
        except (ConnectionError, asyncio.CancelledError, RuntimeError):
            pass
        finally:
            self.servicio.bus.cancelar(cola)
            escritor.close()
            with contextlib.suppress(Exception):
                await escritor.wait_closed()

    # --- enrutado --------------------------------------------------------------------

    async def _responder(self, metodo: str, ruta: str, cuerpo: bytes) -> tuple[str, str, bytes]:
        if ruta.startswith("/api/"):
            try:
                datos = json.loads(cuerpo.decode("utf-8")) if cuerpo else {}
                if not isinstance(datos, dict):
                    raise ValueError("el cuerpo tiene que ser un objeto JSON")
                return await self._api(metodo, ruta, datos)
            except (ValueError, KeyError, TypeError, protocolo.ErrorProtocolo) as error:
                return self._error("400 Bad Request", str(error))
            except dispositivo.ErrorDispositivo as error:
                return self._error("503 Service Unavailable", str(error))
            except RuntimeError as error:
                return self._error("409 Conflict", str(error))
        return self._estatico(ruta)

    @staticmethod
    def _json_ok(datos: Any) -> tuple[str, str, bytes]:
        return "200 OK", "application/json; charset=utf-8", json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")

    @staticmethod
    def _error(estado: str, mensaje: str) -> tuple[str, str, bytes]:
        return estado, "application/json; charset=utf-8", json.dumps({"error": mensaje}, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _estatico(ruta: str) -> tuple[str, str, bytes]:
        nombre = "index.html" if ruta in ("/", "") else ruta.lstrip("/")
        raiz = CARPETA_WEB.resolve()
        destino = (raiz / nombre).resolve()
        try:
            destino.relative_to(raiz)
        except ValueError:
            destino = raiz / "index.html"
        if not destino.is_file():
            return "404 Not Found", "text/plain; charset=utf-8", b"No existe esa pagina."
        tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "image/svg+xml"):
            tipo = f"{tipo}; charset=utf-8"
        return "200 OK", tipo, destino.read_bytes()

    @staticmethod
    def _entero(datos: dict[str, Any], campo: str, minimo: int, maximo: int, opcional: bool = False) -> Optional[int]:
        valor = datos.get(campo)
        if valor is None and opcional:
            return None
        if not isinstance(valor, int) or isinstance(valor, bool) or not minimo <= valor <= maximo:
            raise ValueError(f"«{campo}» tiene que ser un número entre {minimo} y {maximo}")
        return valor

    async def _api(self, metodo: str, ruta: str, datos: dict[str, Any]) -> tuple[str, str, bytes]:
        s = self.servicio
        en_hilo = asyncio.to_thread  # el HID bloquea; fuera del bucle
        ultimo_perfil = protocolo.NUMERO_DE_PERFILES - 1

        if ruta == "/api/estado" and metodo == "GET":
            return self._json_ok(s.resumen())
        if ruta == "/api/opciones" and metodo == "GET":
            return self._json_ok({
                "teclas": sorted(set(protocolo.NOMBRES.values())),
                "raton": list(protocolo.RATON),
                "multimedia": list(CONSUMO),
                "modificadores": list(protocolo.MODIFICADORES),
                "piezas": list(protocolo.NOMBRES_DE_LAS_PIEZAS),
                "gestos": list(protocolo.GESTOS),
                "modos_de_luz": [{"valor": v, "nombre": n} for v, n in protocolo.MODOS_DE_LUZ.items()],
                "atajos_de_dictado": ATAJOS_DE_DICTADO,
                "max_pasos": protocolo.MAX_PASOS,
                "direcciones": ["127.0.0.1", *direcciones_locales()],
                "escuchando_en": self.ajustes.host_panel,
                "equipo": _nombre_del_equipo(),
            })
        if ruta == "/api/registro" and metodo == "GET":
            return self._json_ok({"ruta": str(ruta_registro()), "lineas": _cola_del_registro()})
        if ruta == "/api/ajustes":
            if metodo == "GET":
                return self._json_ok(self.ajustes.como_dict())
            if metodo == "POST":
                return self._json_ok(self._guardar_ajustes(datos))
        if ruta == "/api/pieza" and metodo == "POST":
            perfil = self._entero(datos, "perfil", 0, ultimo_perfil)
            pieza = self._entero(datos, "pieza", 0, protocolo.NUMERO_DE_PIEZAS - 1)
            accion = datos.get("accion")
            if not isinstance(accion, str):
                raise ValueError("falta «accion» (texto: ctrl-c, vol+, rueda-arriba, nada…)")
            return self._json_ok(await en_hilo(s.poner_pieza, perfil, pieza, accion))
        if ruta == "/api/perfil" and metodo == "POST":
            perfil = self._entero(datos, "perfil", 0, ultimo_perfil)
            cambios = {k: v for k, v in datos.items() if k in ("nombre", "teclas", "perillas", "luces_modo", "luces_color")}
            return self._json_ok(await en_hilo(s.poner_perfil, perfil, cambios))
        if ruta == "/api/luces" and metodo == "POST":
            perfil = self._entero(datos, "perfil", 0, ultimo_perfil)
            modo = self._entero(datos, "modo", 0, 255)
            color = datos.get("color")
            if not isinstance(color, str):
                raise ValueError("falta «color» (#RRGGBB)")
            return self._json_ok(await en_hilo(s.poner_luces, perfil, modo, color, bool(datos.get("probar"))))
        if ruta == "/api/aplicar" and metodo == "POST":
            perfil = self._entero(datos, "perfil", 0, ultimo_perfil, opcional=True)
            return self._json_ok(await en_hilo(s.aplicar, perfil))
        if ruta == "/api/restablecer" and metodo == "POST":
            perfil = self._entero(datos, "perfil", 0, ultimo_perfil, opcional=True)
            return self._json_ok(await en_hilo(s.restablecer, perfil))
        if ruta == "/api/escuchar" and metodo == "POST":
            segundos = datos.get("segundos", 10)
            if not isinstance(segundos, (int, float)) or isinstance(segundos, bool):
                raise ValueError("«segundos» tiene que ser un número")
            return self._json_ok(await en_hilo(s.escuchar, float(segundos)))
        return self._error("404 Not Found", f"no hay nada en {ruta}")

    def _guardar_ajustes(self, datos: dict[str, Any]) -> dict[str, Any]:
        cambiados: list[str] = []
        for campo, tipo in _CAMPOS_AJUSTES.items():
            if campo not in datos:
                continue
            valor = datos[campo]
            if tipo is bool and not isinstance(valor, bool):
                raise ValueError(f"«{campo}» tiene que ser verdadero o falso")
            if tipo is str and not isinstance(valor, str):
                raise ValueError(f"«{campo}» tiene que ser texto")
            if campo == "clave_panel" and valor and len(valor) < 6:
                raise ValueError("la clave necesita al menos seis caracteres")
            if campo == "host_panel":
                permitidas = {"127.0.0.1", *direcciones_locales()}
                if valor not in permitidas:
                    raise ValueError(f"esa dirección no es de este equipo; valen {sorted(permitidas)}")
                clave = datos.get("clave_panel") if isinstance(datos.get("clave_panel"), str) else self.ajustes.clave_panel
                if valor != "127.0.0.1" and not clave:
                    raise ValueError("para publicar fuera de este equipo hace falta clave")
            setattr(self.ajustes, campo, valor)
            cambiados.append(campo)
        self.ajustes.guardar()
        self.servicio.publicar("estado")
        if "host_panel" in cambiados:
            asyncio.get_running_loop().call_later(0.8, lambda: asyncio.ensure_future(self._reabrir()))
        return {"guardado": cambiados, "ajustes": self.ajustes.como_dict(), "reabriendo": "host_panel" in cambiados}

    async def _reabrir(self) -> None:
        await self.detener()
        self.puerto = None
        await self.arrancar()
        if self.puerto is None:
            self.ajustes.host_panel = "127.0.0.1"
            self.ajustes.guardar()
            await self.arrancar()
        self.servicio.publicar("estado")
