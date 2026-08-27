"""Pruebas de la aprobación a distancia.

Lo que se comprueba aquí es sobre todo lo que NO debe pasar: que activar esta
función no permita nada por su cuenta, que lo denegado por una regla ni siquiera
llegue a preguntarse, y que el agente nunca se quede esperando para siempre.
"""

from __future__ import annotations

import asyncio
import json
import unittest

from pruebas.base import PruebaAislada
from tecladoia.aprobaciones import ColaAprobaciones
from tecladoia.config import Ajustes
from tecladoia.dispositivo import GestorTeclado
from tecladoia.modelo import Contexto, Decision, MotivoDecision, Veredicto
from tecladoia.servidor import ServidorEnganches
from tecladoia.transporte.simulado import TransporteSimulado


def _veredicto_preguntar() -> Veredicto:
    return Veredicto(Decision.PREGUNTAR, MotivoDecision.PALANCA_MANUAL, 1)


def _contexto() -> Contexto:
    return Contexto(
        agente="claude",
        evento="PermissionRequest",
        herramienta="Bash",
        comando="git push origin main",
    )


class PruebaCola(PruebaAislada):
    def test_lo_contestado_en_la_web_manda(self):
        async def caso():
            cola = ColaAprobaciones()
            tarea = asyncio.create_task(
                cola.preguntar(_contexto(), _veredicto_preguntar(), espera_s=5)
            )
            await asyncio.sleep(0.05)
            pendientes = cola.listar()
            self.assertEqual(len(pendientes), 1)
            self.assertEqual(pendientes[0]["comando"], "git push origin main")

            self.assertTrue(cola.responder(pendientes[0]["id"], "permitir"))
            veredicto = await tarea
            self.assertIs(veredicto.decision, Decision.PERMITIR)
            self.assertIs(veredicto.motivo, MotivoDecision.APROBADA_EN_LA_WEB)
            self.assertEqual(cola.listar(), [])

        asyncio.run(caso())

    def test_denegar_desde_la_web_tambien_manda(self):
        async def caso():
            cola = ColaAprobaciones()
            tarea = asyncio.create_task(
                cola.preguntar(_contexto(), _veredicto_preguntar(), espera_s=5)
            )
            await asyncio.sleep(0.05)
            cola.responder_todas("denegar")
            veredicto = await tarea
            self.assertIs(veredicto.decision, Decision.DENEGAR)
            self.assertIs(veredicto.motivo, MotivoDecision.DENEGADA_EN_LA_WEB)

        asyncio.run(caso())

    def test_si_nadie_contesta_decide_la_persona(self):
        """El plazo es la red de seguridad: sin respuesta, todo sigue igual."""

        async def caso():
            cola = ColaAprobaciones()
            veredicto = await cola.preguntar(
                _contexto(), _veredicto_preguntar(), espera_s=0.15
            )
            self.assertIs(veredicto.decision, Decision.PREGUNTAR)
            self.assertIs(veredicto.motivo, MotivoDecision.SIN_RESPUESTA_EN_LA_WEB)
            self.assertEqual(cola.listar(), [])

        asyncio.run(caso())

    def test_una_respuesta_tardia_no_rompe_nada(self):
        async def caso():
            cola = ColaAprobaciones()
            tarea = asyncio.create_task(
                cola.preguntar(_contexto(), _veredicto_preguntar(), espera_s=0.1)
            )
            identificador = None
            await asyncio.sleep(0.02)
            if pendientes := cola.listar():
                identificador = pendientes[0]["id"]
            await tarea
            self.assertFalse(cola.responder(identificador or "p1", "permitir"))

        asyncio.run(caso())

    def test_solo_se_aceptan_permitir_y_denegar(self):
        cola = ColaAprobaciones()
        with self.assertRaises(ValueError):
            cola.responder("p1", "quizas")

    def test_el_bus_avisa_de_cada_peticion(self):
        async def caso():
            cola = ColaAprobaciones()
            oyente = cola.bus.suscribir()
            tarea = asyncio.create_task(
                cola.preguntar(_contexto(), _veredicto_preguntar(), espera_s=0.1)
            )
            suceso = await asyncio.wait_for(oyente.get(), 1)
            self.assertEqual(suceso["tipo"], "aprobacion_pendiente")
            self.assertEqual(suceso["datos"]["agente"], "claude")
            await tarea

        asyncio.run(caso())


class PruebaServicioConAprobacionRemota(PruebaAislada):
    async def _montar(self, remota: bool, palanca: int = 1):
        ajustes = Ajustes(
            sincronizar_config_agentes=False,
            aprobacion_remota=remota,
            espera_aprobacion_s=3,
        )
        gestor = GestorTeclado(ajustes, TransporteSimulado(palanca=palanca))
        await gestor.conectar()
        return ServidorEnganches(gestor, ajustes)

    def _peticion(self, **contexto) -> str:
        return json.dumps(
            {
                "orden": "evento",
                "agente": "claude",
                "evento": "PermissionRequest",
                "contexto": contexto,
            }
        )

    def test_apagada_no_cambia_nada(self):
        async def caso():
            servidor = await self._montar(remota=False)
            respuesta = await servidor.procesar(self._peticion(comando="git status"))
            self.assertEqual(respuesta["decision"], "preguntar")
            self.assertEqual(len(servidor.aprobaciones), 0)

        asyncio.run(caso())

    def test_encendida_publica_la_peticion_y_espera(self):
        async def caso():
            servidor = await self._montar(remota=True)
            tarea = asyncio.create_task(
                servidor.procesar(self._peticion(herramienta="Bash", comando="git status"))
            )
            await asyncio.sleep(0.1)
            pendientes = servidor.aprobaciones.listar()
            self.assertEqual(len(pendientes), 1)
            servidor.aprobaciones.responder(pendientes[0]["id"], "permitir")

            respuesta = await tarea
            self.assertEqual(respuesta["decision"], "permitir")
            self.assertEqual(
                respuesta["respuesta"]["hookSpecificOutput"]["decision"], "allow"
            )

        asyncio.run(caso())

    def test_lo_que_una_regla_deniega_no_llega_a_preguntarse(self):
        """La red de seguridad no se puede saltar contestando desde la web."""

        async def caso():
            servidor = await self._montar(remota=True)
            respuesta = await servidor.procesar(
                self._peticion(herramienta="Bash", comando="rm -rf /datos")
            )
            self.assertEqual(respuesta["decision"], "denegar")
            self.assertEqual(len(servidor.aprobaciones), 0)

        asyncio.run(caso())

    def test_con_la_palanca_en_automatico_no_se_pregunta(self):
        async def caso():
            servidor = await self._montar(remota=True, palanca=0)
            respuesta = await servidor.procesar(self._peticion(comando="ls -la"))
            self.assertEqual(respuesta["decision"], "permitir")
            self.assertEqual(len(servidor.aprobaciones), 0)

        asyncio.run(caso())


if __name__ == "__main__":
    unittest.main()
