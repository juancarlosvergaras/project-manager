"""Transporte BLE nativo, sobre `bleak`.

`bleak` habla con la pila Bluetooth del sistema (CoreBluetooth en macOS, WinRT
en Windows y BlueZ en Linux), de modo que no hace falta el puente TCP que usaba
el proyecto original en las plataformas no nativas.
"""

from __future__ import annotations

from typing import Optional

from .. import protocolo
from ..registro import obtener
from .base import ErrorTransporte, Transporte, hay_bleak

_log = obtener("ble")

#: Nombres con los que el teclado se anuncia.
NOMBRES_CONOCIDOS = ("ahakey", "vibecoding", "x1")


class TransporteBLE(Transporte):
    """Conexión directa con el teclado por Bluetooth de baja energía."""

    nombre_legible = "BLE nativo"

    def __init__(self, nombre: str = "", tiempo_busqueda_s: float = 8.0) -> None:
        super().__init__()
        self.nombre = nombre
        self.tiempo_busqueda_s = tiempo_busqueda_s
        self._cliente = None
        self._memoria = bytearray()
        self._direccion: Optional[str] = None

    @property
    def conectado(self) -> bool:
        return bool(self._cliente is not None and self._cliente.is_connected)

    async def buscar(self) -> list[tuple[str, str]]:
        """Devuelve los dispositivos compatibles vistos en la búsqueda."""
        if not hay_bleak():
            raise ErrorTransporte(
                "Falta la biblioteca «bleak». Instálala con: pip install 'tecladoia[ble]'"
            )
        from bleak import BleakScanner

        encontrados = await BleakScanner.discover(timeout=self.tiempo_busqueda_s)
        candidatos: list[tuple[str, str]] = []
        for dispositivo in encontrados:
            etiqueta = (dispositivo.name or "").lower()
            if self.nombre:
                if self.nombre.lower() in etiqueta:
                    candidatos.append((dispositivo.address, dispositivo.name or ""))
            elif any(clave in etiqueta for clave in NOMBRES_CONOCIDOS):
                candidatos.append((dispositivo.address, dispositivo.name or ""))
        return candidatos

    async def conectar(self) -> None:
        if not hay_bleak():
            raise ErrorTransporte(
                "Falta la biblioteca «bleak». Instálala con: pip install 'tecladoia[ble]'"
            )
        from bleak import BleakClient

        candidatos = await self.buscar()
        if not candidatos:
            raise ErrorTransporte(
                "No se encontró ningún teclado AhaKey cerca. "
                "Comprueba que está encendido y emparejado."
            )
        self._direccion, nombre = candidatos[0]
        _log.info("Conectando con «%s» (%s)", nombre or "sin nombre", self._direccion)
        cliente = BleakClient(self._direccion)
        await cliente.connect()
        await cliente.start_notify(protocolo.CARACTERISTICA_NOTIFICA, self._al_notificar)
        self._cliente = cliente
        _log.info("Teclado conectado")

    async def desconectar(self) -> None:
        cliente, self._cliente = self._cliente, None
        if cliente is None:
            return
        try:
            await cliente.stop_notify(protocolo.CARACTERISTICA_NOTIFICA)
        except Exception:  # el teclado puede haberse ido antes que nosotros
            pass
        try:
            await cliente.disconnect()
        except Exception:
            pass

    def _al_notificar(self, _caracteristica, datos: bytearray) -> None:
        self._memoria.extend(datos)
        for trama in protocolo.separar_tramas(self._memoria):
            self._entregar(trama)

    async def enviar_comando(self, trama: bytes) -> None:
        await self._escribir(protocolo.CARACTERISTICA_COMANDO, trama)

    async def enviar_datos(self, bloque: bytes) -> None:
        await self._escribir(protocolo.CARACTERISTICA_DATOS, bloque)

    async def _escribir(self, caracteristica: str, carga: bytes) -> None:
        if self._cliente is None or not self._cliente.is_connected:
            raise ErrorTransporte("El teclado no está conectado")
        try:
            await self._cliente.write_gatt_char(caracteristica, bytes(carga), response=False)
        except Exception as error:  # noqa: BLE001 - bleak lanza excepciones variadas
            raise ErrorTransporte(f"Fallo al escribir en el teclado: {error}") from error

    async def bateria(self) -> Optional[int]:
        """Lee el servicio estándar de batería (0x180F)."""
        if self._cliente is None or not self._cliente.is_connected:
            return None
        try:
            crudo = await self._cliente.read_gatt_char(protocolo.CARACTERISTICA_BATERIA)
        except Exception:
            return None
        return crudo[0] if crudo else None

    async def descripcion(self) -> str:
        if self._direccion:
            return f"BLE nativo ({self._direccion})"
        return self.nombre_legible


async def buscar_teclados(tiempo_s: float = 8.0) -> list[tuple[str, str]]:
    """Atajo para la orden ``tecladoia buscar``."""
    return await TransporteBLE(tiempo_busqueda_s=tiempo_s).buscar()


__all__ = ["TransporteBLE", "buscar_teclados"]
