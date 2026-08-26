"""Interfaz común de los transportes."""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from typing import Callable, Optional


class ErrorTransporte(RuntimeError):
    """No se pudo hablar con el teclado."""


def hay_bleak() -> bool:
    """¿Está disponible la pila BLE nativa?"""
    return importlib.util.find_spec("bleak") is not None


class Transporte(ABC):
    """Canal por el que viajan las tramas del protocolo.

    Las implementaciones solo mueven bytes: quien los interpreta es
    :mod:`tecladoia.protocolo`.
    """

    nombre_legible = "transporte"

    def __init__(self) -> None:
        self._al_recibir: Optional[Callable[[bytes], None]] = None

    def escuchar(self, callback: Callable[[bytes], None]) -> None:
        """Registra quién recibe las tramas que llegan del teclado."""
        self._al_recibir = callback

    def _entregar(self, trama: bytes) -> None:
        if self._al_recibir is not None:
            self._al_recibir(trama)

    @property
    @abstractmethod
    def conectado(self) -> bool: ...

    @abstractmethod
    async def conectar(self) -> None: ...

    @abstractmethod
    async def desconectar(self) -> None: ...

    @abstractmethod
    async def enviar_comando(self, trama: bytes) -> None:
        """Escribe en la característica de comandos (0x7343)."""

    @abstractmethod
    async def enviar_datos(self, bloque: bytes) -> None:
        """Escribe en la característica de datos (0x7341), para imágenes OLED."""

    async def descripcion(self) -> str:
        return self.nombre_legible
