"""Transporte a través del puente BLE↔TCP.

Es el mismo formato de paquete que usa el puente original en C#:
``[tipo:1][longitud:2 LE][datos:N]``. Se mantiene para no dejar fuera a quien
ya lo tenga instalado o a las plataformas donde la pila BLE nativa falla.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .. import protocolo
from ..registro import obtener
from .base import ErrorTransporte, Transporte

_log = obtener("puente")

ESCRIBIR_DATOS = 0x01
ESCRIBIR_COMANDO = 0x02
CONSULTAR_ESTADO_BLE = 0x03
CONSULTAR_INFO = 0x04
NOTIFICACION_BLE = 0x81
RESPUESTA_ESTADO_BLE = 0x82
RESPUESTA_INFO = 0x83


def empaquetar(tipo: int, datos: bytes = b"") -> bytes:
    return bytes([tipo]) + len(datos).to_bytes(2, "little") + datos


class TransportePuenteTCP(Transporte):
    nombre_legible = "puente BLE↔TCP"

    def __init__(self, host: str = "127.0.0.1", puerto: int = 9000) -> None:
        super().__init__()
        self.host = host
        self.puerto = puerto
        self._lector: Optional[asyncio.StreamReader] = None
        self._escritor: Optional[asyncio.StreamWriter] = None
        self._tarea: Optional[asyncio.Task] = None
        self._memoria = bytearray()

    @property
    def conectado(self) -> bool:
        return self._escritor is not None and not self._escritor.is_closing()

    async def conectar(self) -> None:
        try:
            self._lector, self._escritor = await asyncio.open_connection(self.host, self.puerto)
        except OSError as error:
            raise ErrorTransporte(
                f"No se pudo abrir el puente en {self.host}:{self.puerto}: {error}"
            ) from error
        self._tarea = asyncio.create_task(self._bucle_lectura())
        _log.info("Puente conectado en %s:%s", self.host, self.puerto)

    async def desconectar(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()
            self._tarea = None
        if self._escritor is not None:
            self._escritor.close()
            try:
                await self._escritor.wait_closed()
            except OSError:
                pass
        self._lector = self._escritor = None

    async def _bucle_lectura(self) -> None:
        assert self._lector is not None
        try:
            while True:
                cabecera = await self._lector.readexactly(3)
                longitud = int.from_bytes(cabecera[1:3], "little")
                cuerpo = await self._lector.readexactly(longitud) if longitud else b""
                if cabecera[0] == NOTIFICACION_BLE:
                    self._memoria.extend(cuerpo)
                    for trama in protocolo.separar_tramas(self._memoria):
                        self._entregar(trama)
        except (asyncio.IncompleteReadError, asyncio.CancelledError, OSError):
            return

    async def enviar_comando(self, trama: bytes) -> None:
        await self._enviar(empaquetar(ESCRIBIR_COMANDO, bytes(trama)))

    async def enviar_datos(self, bloque: bytes) -> None:
        await self._enviar(empaquetar(ESCRIBIR_DATOS, bytes(bloque)))

    async def _enviar(self, paquete: bytes) -> None:
        if self._escritor is None:
            raise ErrorTransporte("El puente no está conectado")
        self._escritor.write(paquete)
        await self._escritor.drain()

    async def descripcion(self) -> str:
        return f"puente BLE↔TCP ({self.host}:{self.puerto})"
