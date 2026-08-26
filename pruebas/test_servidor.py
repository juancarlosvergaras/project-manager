"""Pruebas del servicio de enganches, extremo a extremo con teclado simulado."""

from __future__ import annotations

import asyncio
import json
import unittest

from pruebas.base import PruebaAislada
from tecladoia.config import Ajustes
from tecladoia.dispositivo import GestorTeclado
from tecladoia.modelo import EstadoIA
from tecladoia.servidor import ServidorEnganches
from tecladoia.transporte.simulado import TransporteSimulado


class PruebaServidor(PruebaAislada):
    def montar(self, palanca: int = 1, **opciones) -> tuple[ServidorEnganches, TransporteSimulado]:
        self.simulado = TransporteSimulado(palanca=palanca)
        ajustes = Ajustes(sincronizar_config_agentes=False, **opciones)
        self.gestor = GestorTeclado(ajustes, self.simulado)
        return ServidorEnganches(self.gestor, ajustes), self.simulado

    def correr(self, corrutina):
        return asyncio.run(corrutina)

    async def _peticion(self, servidor, **campos) -> dict:
        return await servidor.procesar(json.dumps({"orden": "evento", **campos}))

    def test_un_evento_de_ciclo_de_vida_solo_mueve_la_luz(self):
        async def caso():
            servidor, simulado = self.montar()
            await self.gestor.conectar()
            respuesta = await self._peticion(servidor, agente="claude", evento="SessionStart")
            await asyncio.sleep(0.05)
            self.assertTrue(respuesta["ok"])
            self.assertIsNone(respuesta["decision"])
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.SESION_INICIADA))
        self.correr(caso())

    def test_permiso_con_palanca_automatica(self):
        async def caso():
            servidor, simulado = self.montar(palanca=0)
            await self.gestor.conectar()
            respuesta = await self._peticion(
                servidor, agente="codex", evento="CodexPermissionRequest",
                contexto={"herramienta": "Bash", "comando": "ls"},
            )
            self.assertEqual(respuesta["decision"], "permitir")
            self.assertEqual(
                respuesta["respuesta"]["hookSpecificOutput"]["decision"], {"behavior": "allow"}
            )
        self.correr(caso())

    def test_permiso_con_palanca_manual(self):
        async def caso():
            servidor, _ = self.montar(palanca=1)
            await self.gestor.conectar()
            respuesta = await self._peticion(
                servidor, agente="claude", evento="PermissionRequest",
                contexto={"comando": "ls"},
            )
            self.assertEqual(respuesta["decision"], "preguntar")
            self.assertEqual(
                respuesta["respuesta"]["hookSpecificOutput"]["decision"], "escalate"
            )
        self.correr(caso())

    def test_una_regla_bloquea_aunque_la_palanca_este_en_automatico(self):
        async def caso():
            servidor, _ = self.montar(palanca=0)
            await self.gestor.conectar()
            respuesta = await self._peticion(
                servidor, agente="claude", evento="PermissionRequest",
                contexto={"herramienta": "Bash", "comando": "sudo rm -rf /"},
            )
            self.assertEqual(respuesta["decision"], "denegar")
            self.assertEqual(respuesta["palanca"], 0)
        self.correr(caso())

    def test_sin_teclado_conectado_nunca_se_aprueba(self):
        async def caso():
            servidor, _ = self.montar(palanca=0)
            # a propósito: no se llama a conectar()
            respuesta = await self._peticion(
                servidor, agente="claude", evento="PermissionRequest", contexto={"comando": "ls"},
            )
            self.assertEqual(respuesta["decision"], "preguntar")
            self.assertIsNone(respuesta["palanca"])
        self.correr(caso())

    def test_la_decision_queda_en_la_bitacora(self):
        async def caso():
            servidor, _ = self.montar(palanca=1)
            await self.gestor.conectar()
            await self._peticion(
                servidor, agente="kimi", evento="KimiPreToolUse",
                contexto={"herramienta": "Bash", "comando": "git status"},
            )
            self.assertEqual(len(servidor.historial), 1)
            from tecladoia.registro import leer_bitacora

            anotado = leer_bitacora(5)
            self.assertEqual(anotado[0]["agente"], "kimi")
            self.assertEqual(anotado[0]["decision"], "preguntar")
        self.correr(caso())

    def test_evento_desconocido(self):
        async def caso():
            servidor, _ = self.montar()
            await self.gestor.conectar()
            respuesta = await self._peticion(servidor, agente="claude", evento="NoExiste")
            self.assertFalse(respuesta["ok"])
        self.correr(caso())

    def test_acepta_los_enganches_del_proyecto_original(self):
        """Texto plano y ``{"cmd": ...}``: quien ya los tenga no rehace nada."""
        async def caso():
            servidor, simulado = self.montar()
            await self.gestor.conectar()
            respuesta = await servidor.procesar("SessionStart")
            await asyncio.sleep(0.05)
            self.assertTrue(respuesta["ok"])
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.SESION_INICIADA))

            respuesta = await servidor.procesar('{"cmd":"state","value":3}')
            await asyncio.sleep(0.05)
            self.assertTrue(respuesta["ok"])
            self.assertEqual(simulado.ultimo_estado, 3)

            respuesta = await servidor.procesar('{"cmd":"status"}')
            self.assertTrue(respuesta["conectado"])
        self.correr(caso())

    def test_la_palanca_virtual_manda_sobre_la_fisica(self):
        async def caso():
            servidor, _ = self.montar(palanca=1)
            await self.gestor.conectar()
            await servidor.procesar('{"orden":"palanca","valor":0}')
            respuesta = await self._peticion(
                servidor, agente="claude", evento="PermissionRequest", contexto={"comando": "ls"},
            )
            self.assertEqual(respuesta["decision"], "permitir")

            await servidor.procesar('{"orden":"palanca","valor":null}')
            respuesta = await self._peticion(
                servidor, agente="claude", evento="PermissionRequest", contexto={"comando": "ls"},
            )
            self.assertEqual(respuesta["decision"], "preguntar")
        self.correr(caso())

    def test_el_socket_atiende_de_verdad(self):
        async def caso():
            servidor, _ = self.montar(palanca=0, puerto_hooks=8917)
            await self.gestor.conectar()
            await servidor.arrancar(con_tcp=False)
            try:
                lector, escritor = await asyncio.open_unix_connection(str(servidor.ruta_socket))
                peticion = {"orden": "evento", "agente": "claude", "evento": "PermissionRequest"}
                escritor.write((json.dumps(peticion) + "\n").encode())
                await escritor.drain()
                datos = json.loads(await asyncio.wait_for(lector.readline(), 3))
                escritor.close()
                self.assertEqual(datos["decision"], "permitir")
                self.assertEqual(servidor.ruta_socket.stat().st_mode & 0o777, 0o600)
            finally:
                await servidor.detener()
            self.assertFalse(servidor.ruta_socket.exists())
        self.correr(caso())


class PruebaCache(PruebaAislada):
    def test_la_cache_evita_consultar_el_teclado_en_cada_evento(self):
        async def caso():
            simulado = TransporteSimulado(palanca=0)
            ajustes = Ajustes(sincronizar_config_agentes=False, vigencia_cache_ms=5000)
            gestor = GestorTeclado(ajustes, simulado)
            await gestor.conectar()
            consultas_iniciales = len(simulado.enviadas)
            for _ in range(5):
                self.assertEqual(await gestor.palanca(), 0)
            self.assertEqual(len(simulado.enviadas), consultas_iniciales)
        asyncio.run(caso())

    def test_una_cache_caducada_vuelve_a_preguntar(self):
        async def caso():
            simulado = TransporteSimulado(palanca=1)
            ajustes = Ajustes(sincronizar_config_agentes=False, vigencia_cache_ms=0)
            gestor = GestorTeclado(ajustes, simulado)
            await gestor.conectar()
            antes = len(simulado.enviadas)
            await gestor.palanca()
            self.assertGreater(len(simulado.enviadas), antes)
        asyncio.run(caso())


if __name__ == "__main__":
    unittest.main()
