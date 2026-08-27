"""Aprobaciones a distancia: contestar desde el navegador, no desde la terminal.

Cuando la palanca deja una acción en «preguntar», el agente de IA se detiene y
muestra su propio aviso en la terminal donde corre. Eso está bien si estás
delante de esa terminal. Si no lo estás —el agente corre en otro equipo, o
sencillamente estás en otra habitación con el teléfono en la mano— la petición
se queda esperando a que vuelvas.

Esta cola abre la segunda puerta: la petición aparece también en el panel web y
quien esté mirando puede permitirla o denegarla. Es una función que se activa a
propósito (``aprobacion_remota`` en la configuración) y tiene tres barreras:

* **Solo se consulta lo que ya quedó en «preguntar».** Una acción denegada por
  una regla —``rm -rf`` y compañía— nunca llega hasta aquí.
* **Hay plazo.** Si nadie contesta en ``espera_aprobacion_s`` segundos, se
  responde «preguntar», que es exactamente lo que habría pasado sin esta cola.
* **El agente no se queda colgado nunca**, porque el plazo lo garantiza.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .modelo import Contexto, Decision, MotivoDecision, Veredicto
from .registro import obtener
from .sucesos import Bus

_log = obtener("aprobaciones")

#: Decisiones que se aceptan desde el panel.
RESPUESTAS = {"permitir", "denegar"}

_MOTIVO_DE_RESPUESTA = {
    "permitir": MotivoDecision.APROBADA_EN_LA_WEB,
    "denegar": MotivoDecision.DENEGADA_EN_LA_WEB,
}


@dataclass
class Pendiente:
    """Una petición esperando respuesta humana."""

    identificador: str
    agente: str
    evento: str
    herramienta: Optional[str]
    comando: Optional[str]
    ruta: Optional[str]
    sesion: Optional[str]
    explicacion: str
    creada_en: float
    vence_en: float
    futuro: asyncio.Future = field(repr=False, default=None)  # type: ignore[assignment]

    def segundos_restantes(self) -> float:
        return max(0.0, self.vence_en - time.monotonic())

    def como_json(self) -> dict[str, Any]:
        return {
            "id": self.identificador,
            "agente": self.agente,
            "evento": self.evento,
            "herramienta": self.herramienta,
            "comando": self.comando,
            "ruta": self.ruta,
            "sesion": self.sesion,
            "explicacion": self.explicacion,
            "creada_en": self.creada_en,
            "segundos_restantes": round(self.segundos_restantes(), 1),
        }


class ColaAprobaciones:
    """Guarda las peticiones que esperan respuesta desde el panel."""

    def __init__(self, bus: Optional[Bus] = None) -> None:
        self.bus = bus or Bus()
        self._pendientes: dict[str, Pendiente] = {}
        self._contador = 0

    # --- consulta -------------------------------------------------------
    def listar(self) -> list[dict[str, Any]]:
        """Las peticiones vivas, de la más antigua a la más reciente."""
        self._retirar_caducadas()
        return [p.como_json() for p in self._pendientes.values()]

    def __len__(self) -> int:
        return len(self._pendientes)

    # --- ciclo de una petición ------------------------------------------
    async def preguntar(
        self,
        contexto: Contexto,
        veredicto: Veredicto,
        espera_s: float,
    ) -> Veredicto:
        """Publica la petición y espera respuesta. Devuelve el veredicto final.

        Si nadie contesta dentro del plazo se devuelve el veredicto original,
        de modo que activar esta función nunca cambia el resultado por sí sola:
        como mucho lo adelanta.
        """
        if espera_s <= 0:
            return veredicto

        self._contador += 1
        identificador = f"p{self._contador}"
        ahora = time.monotonic()
        pendiente = Pendiente(
            identificador=identificador,
            agente=contexto.agente,
            evento=contexto.evento,
            herramienta=contexto.herramienta,
            comando=contexto.comando,
            ruta=contexto.ruta,
            sesion=contexto.sesion,
            explicacion=veredicto.explicacion,
            creada_en=time.time(),
            vence_en=ahora + espera_s,
            futuro=asyncio.get_running_loop().create_future(),
        )
        self._pendientes[identificador] = pendiente
        self.bus.publicar("aprobacion_pendiente", pendiente.como_json())

        try:
            respuesta = await asyncio.wait_for(pendiente.futuro, timeout=espera_s)
        except asyncio.TimeoutError:
            self.bus.publicar("aprobacion_caducada", {"id": identificador})
            _log.info(
                "Nadie contestó en el panel a %s en %.0f s: decide la persona",
                contexto.resumen(),
                espera_s,
            )
            return Veredicto(
                veredicto.decision,
                MotivoDecision.SIN_RESPUESTA_EN_LA_WEB,
                veredicto.palanca,
                veredicto.regla,
            )
        except asyncio.CancelledError:
            return veredicto
        finally:
            self._pendientes.pop(identificador, None)

        return Veredicto(
            Decision(respuesta),
            _MOTIVO_DE_RESPUESTA[respuesta],
            veredicto.palanca,
            veredicto.regla,
        )

    def responder(self, identificador: str, respuesta: str) -> bool:
        """Contesta una petición desde el panel. Cierto si llegó a tiempo."""
        respuesta = (respuesta or "").strip().lower()
        if respuesta not in RESPUESTAS:
            raise ValueError(f"Respuesta no válida: {respuesta!r}. Usa permitir o denegar.")
        pendiente = self._pendientes.get(identificador)
        if pendiente is None or pendiente.futuro.done():
            return False
        pendiente.futuro.set_result(respuesta)
        self.bus.publicar(
            "aprobacion_resuelta", {"id": identificador, "respuesta": respuesta}
        )
        return True

    def responder_todas(self, respuesta: str) -> int:
        """Contesta de golpe todo lo que esté esperando."""
        return sum(1 for i in list(self._pendientes) if self.responder(i, respuesta))

    # --- limpieza -------------------------------------------------------
    def _retirar_caducadas(self) -> None:
        for identificador, pendiente in list(self._pendientes.items()):
            if pendiente.segundos_restantes() <= 0 and pendiente.futuro.done():
                self._pendientes.pop(identificador, None)

    def cancelar_todo(self) -> None:
        """Al parar el servicio, nadie debe quedarse esperando."""
        for pendiente in list(self._pendientes.values()):
            if not pendiente.futuro.done():
                pendiente.futuro.cancel()
        self._pendientes.clear()


__all__ = ["ColaAprobaciones", "Pendiente", "RESPUESTAS"]
