"""El túnel hacia el portero: el PC se presenta y deja que le pasen navegadores.

Antes, para que ``minimic.proyectoia.org`` o ``sikaimini.proyectoia.org``
llegaran a un PC había que hacer tres cosas en ese PC: ponerle clave al
panel, publicarlo en su dirección de Tailscale y dejar pasar al cortafuegos.
Y el Mac mini tenía que conocer la dirección de antemano. Cuatro sitios en
los que fallar, y fallaban.

Ahora la conexión la inicia el PC: abre por Tailscale una **conexión de
control** al portero del Mac mini, se presenta (qué aplicación, qué equipo,
si tiene el teclado) y la mantiene con un latido cada diez segundos. Cuando
al portero le llega un navegador, le pide al PC por esa conexión que abra
una **conexión de datos**; el PC la abre, la une con su propio panel, y el
portero empalma navegador y datos. Nada que configurar y ningún puerto
abierto hacia dentro.

**El panel no debe tomar ese tráfico por local.** Viene de Internet, y el
panel deja pasar sin clave lo que llega desde el propio equipo. Por eso las
conexiones de datos hacia el panel salen **desde ``127.0.0.2``**, otra
dirección del bucle local: el panel ve ese origen, no lo cuenta como local y
pide la clave. Si ese origen no se puede usar, el túnel no se abre: antes
mudo que abierto sin clave.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any, Callable

registro = logging.getLogger("minimic.tunel")

LATIDO_S = 10.0
PLAZO_DE_CONEXION_S = 8.0
REINTENTO_S = 15.0
ORIGEN_REMOTO = "127.0.0.2"


class Tunel:
    def __init__(
        self,
        app: str,
        puerto_local: int,
        portero: tuple[str, int],
        estado: Callable[[], dict[str, Any]],
        origen: str = ORIGEN_REMOTO,
    ) -> None:
        self.app = app
        self.puerto_local = puerto_local
        self.portero = portero
        self.estado = estado
        self.origen = origen
        self.conectado = False
        self.ultimo_error = ""
        self.abiertas = 0
        self._parar = asyncio.Event()
        self._tareas: set = set()  # las conexiones de datos en curso, para que nadie las recoja a medias

    # --- lo que ve el panel ------------------------------------------------

    def resumen(self) -> dict[str, Any]:
        return {
            "portero": f"{self.portero[0]}:{self.portero[1]}",
            "conectado": self.conectado,
            "ultimo_error": self.ultimo_error,
            "conexiones": self.abiertas,
        }

    def parar(self) -> None:
        self._parar.set()

    # --- mantener la conexión de control --------------------------------------

    async def mantener(self) -> None:
        while not self._parar.is_set():
            try:
                await self._sesion()
            except (OSError, asyncio.TimeoutError, ConnectionError) as e:
                self.ultimo_error = str(e) or e.__class__.__name__
                registro.debug("túnel: %s", self.ultimo_error)
            except Exception as e:  # noqa: BLE001 - que no muera el hilo por un mensaje raro
                self.ultimo_error = str(e)
                registro.warning("túnel: %s", e)
            self.conectado = False
            try:
                await asyncio.wait_for(self._parar.wait(), REINTENTO_S)
            except asyncio.TimeoutError:
                pass

    async def _sesion(self) -> None:
        lector, escritor = await asyncio.wait_for(asyncio.open_connection(*self.portero), PLAZO_DE_CONEXION_S)
        try:
            escritor.write(self._mensaje(app=self.app))
            await escritor.drain()
            self.conectado = True
            self.ultimo_error = ""
            registro.info("túnel: presentado al portero %s:%s", *self.portero)
            latidos = asyncio.ensure_future(self._latir(escritor))
            try:
                while not self._parar.is_set():
                    linea = await lector.readline()
                    if not linea:
                        break
                    try:
                        orden = json.loads(linea.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(orden, dict) and orden.get("abrir"):
                        tarea = asyncio.ensure_future(self._abrir(str(orden["abrir"])))
                        self._tareas.add(tarea)
                        tarea.add_done_callback(self._tareas.discard)
            finally:
                latidos.cancel()
        finally:
            escritor.close()

    async def _latir(self, escritor: asyncio.StreamWriter) -> None:
        while True:
            await asyncio.sleep(LATIDO_S)
            escritor.write(self._mensaje())
            await escritor.drain()

    def _mensaje(self, **extra: Any) -> bytes:
        datos = dict(self.estado())
        datos.update(extra)
        return (json.dumps(datos, ensure_ascii=False) + "\n").encode("utf-8")

    # --- una conexión de datos -----------------------------------------------

    async def _abrir(self, token: str) -> None:
        try:
            lector_p, escritor_p = await asyncio.wait_for(asyncio.open_connection(*self.portero), PLAZO_DE_CONEXION_S)
        except (OSError, asyncio.TimeoutError) as e:
            self.ultimo_error = f"no se pudo abrir la conexión de datos: {e}"
            return
        try:
            escritor_p.write((json.dumps({"datos": token}) + "\n").encode("utf-8"))
            await escritor_p.drain()
            try:
                lector_l, escritor_l = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self.puerto_local, local_addr=(self.origen, 0)),
                    PLAZO_DE_CONEXION_S,
                )
            except (OSError, asyncio.TimeoutError) as e:
                # Sin el origen remoto el panel tomaría esto por local y no
                # pediría clave. Se cierra y se explica; no se abre a ciegas.
                self.ultimo_error = f"no se pudo hablar con el panel desde {self.origen}: {e}"
                registro.warning("túnel: %s", self.ultimo_error)
                return
        except (OSError, ConnectionError) as e:
            self.ultimo_error = str(e)
            escritor_p.close()
            return
        self.abiertas += 1
        try:
            await asyncio.gather(_empalmar(lector_p, escritor_l), _empalmar(lector_l, escritor_p))
        finally:
            self.abiertas -= 1


async def _empalmar(lector: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    try:
        while True:
            trozo = await lector.read(65536)
            if not trozo:
                break
            escritor.write(trozo)
            await escritor.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            escritor.close()
        except Exception:  # noqa: BLE001
            pass


def analizar_portero(texto: str, puerto_por_omision: int = 8027) -> tuple[str, int] | None:
    """``100.65.52.65:8027`` → ``("100.65.52.65", 8027)``; vacío o raro → None."""
    texto = (texto or "").strip()
    if not texto:
        return None
    anfitrion, _, puerto = texto.rpartition(":")
    if not anfitrion:
        anfitrion, puerto = puerto, ""
    try:
        return anfitrion, int(puerto) if puerto else puerto_por_omision
    except ValueError:
        return None


def se_puede_usar_el_origen(origen: str = ORIGEN_REMOTO) -> bool:
    """¿Se puede salir desde esa dirección del bucle local? (En Windows y Linux sí.)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((origen, 0))
        return True
    except OSError:
        return False
