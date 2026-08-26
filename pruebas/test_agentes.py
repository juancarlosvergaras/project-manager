"""Pruebas de los adaptadores: cada programa de IA espera un JSON distinto."""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada
from tecladoia import agentes
from tecladoia.agentes.claude import AgenteClaude
from tecladoia.agentes.codex import AgenteCodex
from tecladoia.agentes.cursor import AgenteCursor
from tecladoia.agentes.gemini import AgenteGemini
from tecladoia.agentes.generico import AgenteGenerico
from tecladoia.agentes.kimi import AgenteKimi
from tecladoia.modelo import Decision, MotivoDecision, Veredicto

PERMITIR = Veredicto(Decision.PERMITIR, MotivoDecision.PALANCA_AUTOMATICA, 0)
PREGUNTAR = Veredicto(Decision.PREGUNTAR, MotivoDecision.PALANCA_MANUAL, 1)
DENEGAR = Veredicto(Decision.DENEGAR, MotivoDecision.REGLA_DENEGAR, 0, "rm -rf")


class PruebaRegistro(unittest.TestCase):
    def test_los_nombres_internos_no_se_repiten(self):
        """La búsqueda por nombre de evento depende de que sean únicos."""
        vistos: set[str] = set()
        for agente in agentes.AGENTES:
            if agente.id == "generico":
                continue  # usa nombres cortos y solo responde si se le nombra
            for evento in agente.eventos:
                self.assertNotIn(evento.interno, vistos, f"repetido: {evento.interno}")
                vistos.add(evento.interno)

    def test_el_generico_no_secuestra_los_eventos_de_otros(self):
        agente, _ = agentes.buscar_evento("PreToolUse")
        self.assertIs(agente, AgenteClaude)
        self.assertIsNotNone(AgenteGenerico.evento("PreToolUse"))

    def test_cada_agente_tiene_un_evento_que_decide(self):
        for agente in agentes.AGENTES:
            with self.subTest(agente=agente.id):
                self.assertTrue(any(e.permiso for e in agente.eventos))

    def test_se_localiza_el_agente_por_el_nombre_del_evento(self):
        agente, evento = agentes.buscar_evento("KimiPreToolUse")
        self.assertIs(agente, AgenteKimi)
        self.assertTrue(evento.permiso)


class PruebaRespuestas(unittest.TestCase):
    def test_claude_usa_el_esquema_vigente_de_decision(self):
        salida = AgenteClaude.respuesta(AgenteClaude.evento("PermissionRequest"), PERMITIR)
        decision = salida["hookSpecificOutput"]["decision"]
        self.assertEqual(decision, "allow")
        self.assertIsInstance(decision, str)  # el esquema antiguo anidaba un objeto

    def test_claude_escala_en_manual(self):
        salida = AgenteClaude.respuesta(AgenteClaude.evento("PermissionRequest"), PREGUNTAR)
        self.assertEqual(salida["hookSpecificOutput"]["decision"], "escalate")

    def test_claude_bloquea_en_pretooluse_solo_si_hay_regla(self):
        evento = AgenteClaude.evento("PreToolUse")
        self.assertEqual(AgenteClaude.respuesta(evento, PREGUNTAR), {})
        salida = AgenteClaude.respuesta(evento, DENEGAR)
        self.assertEqual(salida["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_codex_devuelve_objeto_vacio_en_el_ciclo_de_vida(self):
        self.assertEqual(AgenteCodex.respuesta(AgenteCodex.evento("CodexStop"), PERMITIR), {})

    def test_codex_calla_cuando_hay_que_preguntar(self):
        salida = AgenteCodex.respuesta(AgenteCodex.evento("CodexPermissionRequest"), PREGUNTAR)
        self.assertNotIn("decision", salida["hookSpecificOutput"])

    def test_cursor_solo_entiende_permitir_o_denegar(self):
        evento = AgenteCursor.evento("preToolUse")
        self.assertEqual(AgenteCursor.respuesta(evento, PERMITIR)["permission"], "allow")
        self.assertEqual(AgenteCursor.respuesta(evento, PREGUNTAR)["permission"], "deny")

    def test_kimi_bloquea_con_motivo_en_manual(self):
        salida = AgenteKimi.respuesta(AgenteKimi.evento("KimiPreToolUse"), PREGUNTAR)
        self.assertEqual(salida["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("palanca", salida["hookSpecificOutput"]["permissionDecisionReason"])

    def test_gemini_deja_pasar_su_propia_confirmacion(self):
        evento = AgenteGemini.evento("GeminiBeforeTool")
        self.assertEqual(AgenteGemini.respuesta(evento, PERMITIR)["decision"], "allow")
        self.assertNotIn("decision", AgenteGemini.respuesta(evento, PREGUNTAR))
        self.assertEqual(AgenteGemini.respuesta(evento, DENEGAR)["decision"], "deny")

    def test_el_generico_explica_la_decision_en_espanol(self):
        salida = AgenteGenerico.respuesta(AgenteGenerico.evento("PreToolUse"), PREGUNTAR)
        self.assertEqual(salida["decision"], "preguntar")
        self.assertFalse(salida["automatica"])
        self.assertIn("persona", salida["explicacion"])


class PruebaSincronizacion(PruebaAislada):
    def test_codex_alinea_approval_policy_con_la_palanca(self):
        ruta = self.casa / ".codex" / "config.toml"
        ruta.parent.mkdir(parents=True)
        ruta.write_text('model = "gpt-5"\n\n[features]\nhooks = true\n', encoding="utf-8")

        AgenteCodex.sincronizar_palanca(True)
        self.assertIn('approval_policy = "never"', ruta.read_text(encoding="utf-8"))

        AgenteCodex.sincronizar_palanca(False)
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn('approval_policy = "untrusted"', texto)
        self.assertNotIn('approval_policy = "never"', texto)
        # La clave debe quedar por encima de la primera sección.
        self.assertLess(texto.index("approval_policy"), texto.index("[features]"))

    def test_codex_no_toca_una_configuracion_inexistente(self):
        self.assertIsNone(AgenteCodex.sincronizar_palanca(True))

    def test_kimi_enciende_y_apaga_default_yolo(self):
        ruta = self.casa / ".kimi" / "config.toml"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("default_yolo = false\n", encoding="utf-8")
        AgenteKimi.sincronizar_palanca(True)
        self.assertIn("default_yolo = true", ruta.read_text(encoding="utf-8"))
        AgenteKimi.sincronizar_palanca(False)
        self.assertIn("default_yolo = false", ruta.read_text(encoding="utf-8"))

    def test_cursor_amplia_y_recorta_la_lista_de_terminal(self):
        AgenteCursor.sincronizar_palanca(True)
        permisos = AgenteCursor.ruta_permisos()
        lista = __import__("json").loads(permisos.read_text(encoding="utf-8"))
        self.assertIn("git", lista["terminalAllowlist"])
        AgenteCursor.sincronizar_palanca(False)
        lista = __import__("json").loads(permisos.read_text(encoding="utf-8"))
        self.assertNotIn("git", lista["terminalAllowlist"])

    def test_cursor_respeta_lo_que_la_persona_ya_tenia(self):
        permisos = AgenteCursor.ruta_permisos()
        permisos.parent.mkdir(parents=True)
        permisos.write_text('{"terminalAllowlist": ["mi-orden"]}', encoding="utf-8")
        AgenteCursor.sincronizar_palanca(True)
        AgenteCursor.sincronizar_palanca(False)
        lista = __import__("json").loads(permisos.read_text(encoding="utf-8"))
        self.assertEqual(lista["terminalAllowlist"], ["mi-orden"])


if __name__ == "__main__":
    unittest.main()
