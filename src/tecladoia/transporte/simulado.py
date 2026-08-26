"""Teclado simulado.

Reproduce las respuestas del firmware en memoria. Sirve para tres cosas:
probar la aplicación sin hardware, permitir que alguien sin teclado use el
resto del sistema, y hacer que la suite de pruebas sea determinista.
"""

from __future__ import annotations

import asyncio

from .. import protocolo
from .base import Transporte


class TransporteSimulado(Transporte):
    """Emula un AhaKey-X1 con batería llena y la palanca en manual."""

    nombre_legible = "teclado simulado"

    def __init__(
        self,
        palanca: int = 1,
        bateria: int = 100,
        retardo_s: float = 0.0,
    ) -> None:
        super().__init__()
        self.palanca = palanca
        self.bateria = bateria
        self.retardo_s = retardo_s
        self.modo_luz = 0
        self.modo_trabajo = 0
        self.brillo = 35
        self.ultimo_estado: int | None = None
        #: Todas las tramas escritas, en orden. Las pruebas las inspeccionan.
        self.enviadas: list[bytes] = []
        self.bloques_datos: list[bytes] = []
        self._conectado = False

    @property
    def conectado(self) -> bool:
        return self._conectado

    async def conectar(self) -> None:
        self._conectado = True

    async def desconectar(self) -> None:
        self._conectado = False

    async def enviar_comando(self, trama: bytes) -> None:
        if not self._conectado:
            raise RuntimeError("El teclado simulado no está conectado")
        self.enviadas.append(bytes(trama))
        if self.retardo_s:
            await asyncio.sleep(self.retardo_s)
        self._responder(trama)

    async def enviar_datos(self, bloque: bytes) -> None:
        self.bloques_datos.append(bytes(bloque))

    def _responder(self, trama: bytes) -> None:
        comando = protocolo.comando_de(trama)
        cuerpo = protocolo.carga_util(trama)
        if comando == protocolo.Comando.CONSULTAR_ESTADO:
            self._entregar(self._trama_estado())
        elif comando == protocolo.Comando.ACTUALIZAR_ESTADO and cuerpo:
            self.ultimo_estado = cuerpo[0]
            # El firmware devuelve un acuse corto que NO contiene la palanca.
            self._entregar(protocolo.construir_trama(protocolo.Comando.ACTUALIZAR_ESTADO, b"\x00"))
        elif comando == protocolo.Comando.EFECTO_LUZ and cuerpo:
            self.modo_luz = cuerpo[0]
        elif comando == protocolo.Comando.BRILLO_LUZ and cuerpo:
            self.brillo = cuerpo[0]
        elif comando == protocolo.Comando.MODO_TRABAJO and cuerpo:
            self.modo_trabajo = cuerpo[0]

    def _trama_estado(self) -> bytes:
        cuerpo = bytes(
            [
                self.bateria & 0xFF,
                50,
                1,
                0,
                self.modo_trabajo & 0xFF,
                self.modo_luz & 0xFF,
                self.palanca & 0xFF,
                self.brillo & 0xFF,
            ]
        )
        return protocolo.construir_trama(protocolo.Comando.CONSULTAR_ESTADO, cuerpo)

    def mover_palanca(self, valor: int) -> None:
        """Simula que alguien mueve la palanca física."""
        self.palanca = int(valor)
        self._entregar(self._trama_estado())
