"""Pruebas del servicio de enganches, extremo a extremo con teclado simulado."""

from __future__ import annotations

import asyncio
import json
import os
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

    @unittest.skipIf(os.name == "nt", "Windows no tiene sockets de dominio Unix")
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


class PruebaBarraEnReposo(PruebaAislada):
    """La barra no debe quedarse animada cuando ya no hay nadie trabajando."""

    def montar(self, **opciones):
        simulado = TransporteSimulado(palanca=1)
        ajustes = Ajustes(sincronizar_config_agentes=False, **opciones)
        # Aquí se prueba el reposo, no el reparto por modos: se deja el modo
        # activo sin dueño para que lo mueva cualquier programa.
        for modo in ajustes.modos:
            modo.agente = ""
        gestor = GestorTeclado(ajustes, simulado)
        return ServidorEnganches(gestor, ajustes), gestor, simulado

    def test_un_momento_pasajero_vuelve_solo_al_reposo(self):
        async def caso():
            servidor, gestor, simulado = self.montar(milisegundos_estado_breve=30)
            await gestor.conectar()
            await servidor.procesar(
                json.dumps({"orden": "evento", "agente": "claude", "evento": "PostToolUse"})
            )
            await asyncio.sleep(0.02)
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.HERRAMIENTA_TERMINADA))
            await asyncio.sleep(0.15)
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.DETENIDO))
            self.assertIsNone(servidor.agente_activo)
        asyncio.run(caso())

    def test_un_momento_sostenido_no_se_apaga_antes_de_tiempo(self):
        async def caso():
            servidor, gestor, simulado = self.montar(milisegundos_estado_breve=30)
            await gestor.conectar()
            await servidor.procesar(
                json.dumps({"orden": "evento", "agente": "claude", "evento": "PreToolUse"})
            )
            await asyncio.sleep(0.15)
            # Sigue trabajando: la luz azul se queda hasta que el vigilante actúe.
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.HERRAMIENTA_EN_CURSO))
            self.assertEqual(servidor.agente_activo, "claude")
        asyncio.run(caso())

    def test_el_vigilante_apaga_la_barra_si_el_agente_desaparece(self):
        """Un agente cerrado de golpe no emite su evento de cierre."""
        async def caso():
            servidor, gestor, simulado = self.montar(segundos_hasta_reposo=5, puerto_hooks=8953)
            await gestor.conectar()
            await servidor.arrancar(con_tcp=False)
            try:
                await servidor.procesar(
                    json.dumps({"orden": "evento", "agente": "claude", "evento": "PreToolUse"})
                )
                await asyncio.sleep(0.05)
                self.assertEqual(simulado.ultimo_estado, int(EstadoIA.HERRAMIENTA_EN_CURSO))
                # Se finge que el último evento fue hace mucho.
                servidor.ultimo_evento_en -= 60
                await asyncio.sleep(0.8)  # el vigilante mira cada medio segundo
                self.assertEqual(simulado.ultimo_estado, int(EstadoIA.DETENIDO))
                self.assertIsNone(servidor.agente_activo)
            finally:
                await servidor.detener()
        asyncio.run(caso())

    def test_el_cierre_de_sesion_libera_la_barra(self):
        async def caso():
            servidor, gestor, simulado = self.montar()
            await gestor.conectar()
            await servidor.procesar(
                json.dumps({"orden": "evento", "agente": "codex", "evento": "CodexPreToolUse"})
            )
            await asyncio.sleep(0.02)
            self.assertEqual(servidor.agente_activo, "codex")
            await servidor.procesar(
                json.dumps({"orden": "evento", "agente": "codex", "evento": "CodexStop"})
            )
            await asyncio.sleep(0.02)
            self.assertIsNone(servidor.agente_activo)
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.DETENIDO))
        asyncio.run(caso())

    def test_el_ultimo_agente_en_hablar_se_queda_con_la_barra(self):
        async def caso():
            servidor, gestor, _ = self.montar()
            await gestor.conectar()
            await servidor.procesar(
                json.dumps({"orden": "evento", "agente": "claude", "evento": "PreToolUse"})
            )
            self.assertEqual(servidor.agente_activo, "claude")
            await servidor.procesar(
                json.dumps({"orden": "evento", "agente": "codex", "evento": "CodexPreToolUse"})
            )
            await asyncio.sleep(0.02)
            self.assertEqual(servidor.agente_activo, "codex")
            resumen = await servidor.procesar('{"orden":"estado"}')
            self.assertEqual(resumen["agente_activo"], "codex")
            self.assertIsNotNone(resumen["segundos_sin_eventos"])
        asyncio.run(caso())


class PruebaModosIndependientes(PruebaAislada):
    """Cada modo del teclado atiende solo al programa que manda en él."""

    def montar(self, modo_activo: int = 0):
        simulado = TransporteSimulado(palanca=1)
        simulado.modo_trabajo = modo_activo
        ajustes = Ajustes(sincronizar_config_agentes=False)
        gestor = GestorTeclado(ajustes, simulado)
        return ServidorEnganches(gestor, ajustes), gestor, simulado

    def _evento(self, agente: str, evento: str) -> str:
        return json.dumps({"orden": "evento", "agente": agente, "evento": evento})

    def test_el_dueno_del_modo_enciende_la_barra(self):
        async def caso():
            servidor, gestor, simulado = self.montar(modo_activo=0)  # Claude
            await gestor.conectar()
            await servidor.procesar(self._evento("claude", "PreToolUse"))
            await asyncio.sleep(0.05)
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.HERRAMIENTA_EN_CURSO))
        asyncio.run(caso())

    def test_otro_programa_no_toca_la_barra_de_un_modo_ajeno(self):
        """Estando en el modo de ChatGPT, Claude Code no debe encender nada."""

        async def caso():
            servidor, gestor, simulado = self.montar(modo_activo=1)  # ChatGPT
            await gestor.conectar()
            antes = simulado.ultimo_estado
            await servidor.procesar(self._evento("claude", "PreToolUse"))
            await asyncio.sleep(0.05)
            self.assertEqual(simulado.ultimo_estado, antes)
            # Se anota igual, para poder verlo luego en el panel.
            self.assertTrue(servidor.avisos)
            self.assertFalse(servidor.avisos[-1]["atendido"])
        asyncio.run(caso())

    def test_un_modo_sin_dueno_lo_mueve_cualquiera(self):
        async def caso():
            servidor, gestor, simulado = self.montar(modo_activo=3)  # el libre
            await gestor.conectar()
            await servidor.procesar(self._evento("codex", "CodexPreToolUse"))
            await asyncio.sleep(0.05)
            self.assertEqual(simulado.ultimo_estado, int(EstadoIA.HERRAMIENTA_EN_CURSO))
        asyncio.run(caso())


if __name__ == "__main__":
    unittest.main()
