"""Transportes hacia el teclado: BLE nativo, puente TCP y simulador."""

from __future__ import annotations

from .base import ErrorTransporte, Transporte
from .simulado import TransporteSimulado

__all__ = ["Transporte", "ErrorTransporte", "TransporteSimulado", "crear"]


def crear(ajustes) -> Transporte:
    """Devuelve el transporte que corresponde a los ajustes.

    Con ``transporte = "auto"`` no se elige uno y ya: se prueban por orden todos
    los caminos posibles y se usa el primero que conteste. Hace falta porque en
    Windows el camino bueno no es el evidente —el teclado emparejado deja de
    anunciarse y solo se llega a él por la lista de dispositivos del sistema—,
    mientras que en macOS y Linux sí vale el BLE de siempre.
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
    if elegido == "windows":
        from .windows_emparejado import TransporteWindowsEmparejado

        return TransporteWindowsEmparejado(ajustes.nombre_dispositivo)

    from .automatico import TransporteAutomatico

    return TransporteAutomatico(ajustes)
