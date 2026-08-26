"""Motor de aprobación: decide si una acción del agente sigue o se detiene.

Reglas del juego, en orden:

1. Si la configuración fija el modo (``siempre_preguntar`` o ``siempre_permitir``),
   eso manda.
2. Las reglas restrictivas (``denegar`` y ``preguntar``) ganan siempre, incluso
   con la palanca en automático: son la red de seguridad para ``rm -rf`` y
   compañía.
3. Las reglas permisivas solo actúan si se habilitan a propósito.
4. Si nada de lo anterior aplica, decide la palanca: 0 es automático y cualquier
   otra cosa -incluida la falta de lectura- devuelve el control a la persona.

El cuarto punto es el corazón del diseño a prueba de fallos: **ante la duda,
nunca se aprueba solo.**
"""

from __future__ import annotations

from typing import Iterable, Optional

from .config import Ajustes, Regla
from .modelo import Contexto, Decision, MotivoDecision, Veredicto

_PRIORIDAD = {"denegar": 3, "preguntar": 2, "permitir": 1}

_MOTIVO_DE_REGLA = {
    "denegar": MotivoDecision.REGLA_DENEGAR,
    "preguntar": MotivoDecision.REGLA_PREGUNTAR,
    "permitir": MotivoDecision.REGLA_PERMITIR,
}


def _texto_a_comparar(contexto: Contexto) -> str:
    piezas = [contexto.herramienta or "", contexto.comando or "", contexto.ruta or ""]
    return " ".join(piezas).lower()


def regla_aplicable(reglas: Iterable[Regla], contexto: Contexto) -> Optional[Regla]:
    """Devuelve la regla más restrictiva que coincide con el contexto."""
    objetivo = _texto_a_comparar(contexto)
    if not objetivo.strip():
        return None
    mejor: Optional[Regla] = None
    for regla in reglas:
        patron = (regla.patron or "").strip().lower()
        if not patron or patron not in objetivo:
            continue
        agente = (regla.agente or "*").lower()
        if agente not in ("*", "", contexto.agente.lower()):
            continue
        peso = _PRIORIDAD.get(regla.decision, 0)
        if mejor is None or peso > _PRIORIDAD.get(mejor.decision, 0):
            mejor = regla
    return mejor


def decidir(
    ajustes: Ajustes,
    palanca: Optional[int],
    contexto: Contexto,
    conectado: bool = True,
) -> Veredicto:
    """Resuelve una petición de permiso."""
    modo = (ajustes.modo_aprobacion or "palanca").lower()
    if modo == "siempre_preguntar":
        return Veredicto(Decision.PREGUNTAR, MotivoDecision.MODO_FORZADO, palanca)
    if modo == "siempre_permitir":
        return Veredicto(Decision.PERMITIR, MotivoDecision.MODO_FORZADO, palanca)

    regla = regla_aplicable(ajustes.reglas, contexto)
    if regla is not None and regla.decision in ("denegar", "preguntar"):
        return Veredicto(
            Decision(regla.decision),
            _MOTIVO_DE_REGLA[regla.decision],
            palanca,
            regla.patron,
        )

    if palanca is None:
        motivo = (
            MotivoDecision.SIN_LECTURA_DE_PALANCA if conectado else MotivoDecision.SIN_CONEXION
        )
        return Veredicto(Decision.PREGUNTAR, motivo, None)

    if palanca == 0:
        return Veredicto(Decision.PERMITIR, MotivoDecision.PALANCA_AUTOMATICA, palanca)

    if regla is not None and regla.decision == "permitir" and ajustes.reglas_permisivas:
        return Veredicto(Decision.PERMITIR, MotivoDecision.REGLA_PERMITIR, palanca, regla.patron)

    return Veredicto(Decision.PREGUNTAR, MotivoDecision.PALANCA_MANUAL, palanca)
