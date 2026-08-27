"""Transporte que prueba, por orden, todo lo que puede llevar al teclado.

Hay más de un camino hasta un AhaKey y ninguno funciona siempre:

* **Bluetooth directo.** Es el bueno: sin intermediarios y sin instalar nada.
  Pero en Windows solo se le puede enganchar mientras el teclado se está
  anunciando. En cuanto el sistema lo toma como teclado normal deja de
  anunciarse, y entonces ni el rastreo lo ve ni vale su dirección —que además
  va rotando, que para eso es un dispositivo con privacidad—.
* **El puente BLE↔TCP** del fabricante. Si está corriendo, tiene el teclado
  tomado y lo comparte por el puerto 9000. Entonces el camino es ese, y además
  es el único mientras ese programa esté abierto.

Elegir a mano cuál toca es tarea del programa, no de la persona. Esta clase los
prueba en orden y se queda con el primero que conteste; cuando el que estaba
usando se cae, la siguiente reconexión vuelve a probar desde arriba.
"""

from __future__ import annotations

from typing import Callable, Optional

from ..registro import obtener
from .base import ErrorTransporte, Transporte, hay_bleak

_log = obtener("transporte")


class TransporteAutomatico(Transporte):
    """Envoltorio que elige el camino disponible en cada momento."""

    nombre_legible = "automático"

    def __init__(self, ajustes) -> None:
        super().__init__()
        self.ajustes = ajustes
        self._elegido: Optional[Transporte] = None

    # --- construcción de candidatos --------------------------------------
    def _candidatos(self) -> list[Transporte]:
        from .ble import TransporteBLE
        from .puente_tcp import TransportePuenteTCP
        from .windows_emparejado import TransporteWindowsEmparejado, hay_winrt

        lista: list[Transporte] = []
        if hay_winrt():
            lista.append(TransporteWindowsEmparejado(self.ajustes.nombre_dispositivo))
        if hay_bleak():
            lista.append(
                TransporteBLE(
                    nombre=self.ajustes.nombre_dispositivo,
                    direccion=getattr(self.ajustes, "direccion_dispositivo", ""),
                )
            )
        lista.append(
            TransportePuenteTCP(self.ajustes.puente_host, self.ajustes.puente_puerto)
        )
        return lista

    # --- Transporte -------------------------------------------------------
    def escuchar(self, callback: Callable[[bytes], None]) -> None:
        super().escuchar(callback)
        if self._elegido is not None:
            self._elegido.escuchar(callback)

    @property
    def conectado(self) -> bool:
        return self._elegido is not None and self._elegido.conectado

    async def conectar(self) -> None:
        motivos: list[str] = []
        for candidato in self._candidatos():
            candidato.escuchar(self._entregar)
            try:
                await candidato.conectar()
            except ErrorTransporte as error:
                motivos.append(f"{candidato.nombre_legible}: {error}")
                continue
            except Exception as error:  # noqa: BLE001 - la pila BLE lanza de todo
                motivos.append(f"{candidato.nombre_legible}: {error}")
                continue
            self._elegido = candidato
            _log.info("Teclado alcanzado por %s", candidato.nombre_legible)
            return
        self._elegido = None
        raise ErrorTransporte(
            "No se pudo llegar al teclado por ningún camino. " + " · ".join(motivos)
        )

    async def desconectar(self) -> None:
        if self._elegido is not None:
            await self._elegido.desconectar()
            self._elegido = None

    async def enviar_comando(self, trama: bytes) -> None:
        await self._exigir().enviar_comando(trama)

    async def enviar_datos(self, bloque: bytes) -> None:
        await self._exigir().enviar_datos(bloque)

    def _exigir(self) -> Transporte:
        if self._elegido is None:
            raise ErrorTransporte("El teclado no está conectado")
        return self._elegido

    async def descripcion(self) -> str:
        if self._elegido is None:
            return "sin conexión"
        return await self._elegido.descripcion()

    @property
    def direccion(self) -> Optional[str]:
        """La dirección del teclado, si el camino elegido la conoce."""
        return getattr(self._elegido, "_direccion", None)


__all__ = ["TransporteAutomatico"]
