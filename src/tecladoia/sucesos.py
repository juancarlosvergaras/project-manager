"""Bus de sucesos: lo que pasa dentro del servicio llega al navegador.

El panel web no pregunta «¿ha cambiado algo?» cada pocos segundos: se queda
escuchando. Este módulo es la pieza intermedia. Quien produce algo interesante
—una decisión, un cambio de palanca, una aprobación pendiente— lo publica aquí,
y cada pestaña abierta recibe su copia por un canal de eventos del servidor.

Es deliberadamente pequeño y sin dependencias: una cola por suscriptor y un
tamaño máximo. Si un navegador se queda atrás —una pestaña dormida, una red
lenta— se le descartan los sucesos más viejos en vez de dejar que la memoria
del servicio crezca sin freno.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

#: Sucesos que se guardan por suscriptor antes de empezar a descartar los viejos.
MAXIMO_EN_COLA = 200


class Bus:
    """Reparte sucesos a todas las pestañas abiertas del panel."""

    def __init__(self) -> None:
        self._colas: set[asyncio.Queue] = set()
        self._ultimo_id = 0

    @property
    def oyentes(self) -> int:
        """Cuántas pestañas hay escuchando ahora mismo."""
        return len(self._colas)

    def suscribir(self) -> asyncio.Queue:
        cola: asyncio.Queue = asyncio.Queue(maxsize=MAXIMO_EN_COLA)
        self._colas.add(cola)
        return cola

    def cancelar(self, cola: asyncio.Queue) -> None:
        self._colas.discard(cola)

    def publicar(self, tipo: str, datos: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Envía un suceso a todos los suscriptores. Nunca bloquea."""
        self._ultimo_id += 1
        suceso = {"id": self._ultimo_id, "tipo": tipo, "datos": datos or {}}
        for cola in list(self._colas):
            self._encolar(cola, suceso)
        return suceso

    @staticmethod
    def _encolar(cola: asyncio.Queue, suceso: dict[str, Any]) -> None:
        """Mete el suceso; si la cola está llena, tira el más viejo.

        Perder un suceso antiguo es preferible a bloquear al servicio: el panel
        siempre puede volver a pedir el estado completo con ``/api/estado``.
        """
        while True:
            try:
                cola.put_nowait(suceso)
                return
            except asyncio.QueueFull:
                try:
                    cola.get_nowait()
                except asyncio.QueueEmpty:
                    return


__all__ = ["Bus", "MAXIMO_EN_COLA"]
