"""Transportes hacia el teclado: BLE nativo, puente TCP y simulador."""

from __future__ import annotations

from .base import ErrorTransporte, Transporte
from .simulado import TransporteSimulado

__all__ = ["Transporte", "ErrorTransporte", "TransporteSimulado", "crear"]


def crear(ajustes) -> Transporte:
    """Devuelve el transporte que corresponde a los ajustes.

    Con ``transporte = "auto"`` se prefiere BLE nativo y, si la biblioteca
    ``bleak`` no está instalada, se cae al puente TCP; si tampoco lo hay, se
    trabaja en modo simulado para que la aplicación siga siendo usable.
    """
    from .base import hay_bleak
    from .ble import TransporteBLE
    from .puente_tcp import TransportePuenteTCP

    elegido = (ajustes.transporte or "auto").lower()
    if elegido == "simulado":
        return TransporteSimulado()
    if elegido == "ble":
        return TransporteBLE(
            nombre=ajustes.nombre_dispositivo, direccion=ajustes.direccion_dispositivo
        )
    if elegido == "puente":
        return TransportePuenteTCP(ajustes.puente_host, ajustes.puente_puerto)
    if hay_bleak():
        return TransporteBLE(
            nombre=ajustes.nombre_dispositivo, direccion=ajustes.direccion_dispositivo
        )
    return TransportePuenteTCP(ajustes.puente_host, ajustes.puente_puerto)
