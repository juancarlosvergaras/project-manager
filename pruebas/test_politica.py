"""Pruebas del motor de aprobación: es la pieza con consecuencias reales."""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada  # noqa: F401
from tecladoia.config import Ajustes, Regla
from tecladoia.modelo import Contexto, Decision, MotivoDecision
from tecladoia.politica import decidir, regla_aplicable


def _contexto(**extra) -> Contexto:
    base = {"agente": "codex", "evento": "PreToolUse"}
    base.update(extra)
    return Contexto(**base)


class PruebaPalanca(unittest.TestCase):
    def setUp(self) -> None:
        self.ajustes = Ajustes()

    def test_palanca_en_cero_aprueba(self):
        veredicto = decidir(self.ajustes, 0, _contexto(herramienta="Read"))
        self.assertIs(veredicto.decision, Decision.PERMITIR)
        self.assertIs(veredicto.motivo, MotivoDecision.PALANCA_AUTOMATICA)

    def test_cualquier_otra_posicion_devuelve_la_decision(self):
        for posicion in (1, 2, 7):
            with self.subTest(posicion=posicion):
                self.assertIs(
                    decidir(self.ajustes, posicion, _contexto()).decision, Decision.PREGUNTAR
                )

    def test_sin_lectura_de_palanca_nunca_aprueba(self):
        veredicto = decidir(self.ajustes, None, _contexto(), conectado=True)
        self.assertIs(veredicto.decision, Decision.PREGUNTAR)
        self.assertIs(veredicto.motivo, MotivoDecision.SIN_LECTURA_DE_PALANCA)

    def test_sin_conexion_nunca_aprueba(self):
        veredicto = decidir(self.ajustes, None, _contexto(), conectado=False)
        self.assertIs(veredicto.decision, Decision.PREGUNTAR)
        self.assertIs(veredicto.motivo, MotivoDecision.SIN_CONEXION)


class PruebaReglas(unittest.TestCase):
    def setUp(self) -> None:
        self.ajustes = Ajustes()

    def test_una_regla_de_bloqueo_gana_a_la_palanca_automatica(self):
        veredicto = decidir(self.ajustes, 0, _contexto(comando="rm -rf /datos"))
        self.assertIs(veredicto.decision, Decision.DENEGAR)
        self.assertEqual(veredicto.regla, "rm -rf")

    def test_una_regla_de_confirmacion_gana_a_la_palanca_automatica(self):
        veredicto = decidir(self.ajustes, 0, _contexto(comando="git push --force origin main"))
        self.assertIs(veredicto.decision, Decision.PREGUNTAR)
        self.assertIs(veredicto.motivo, MotivoDecision.REGLA_PREGUNTAR)

    def test_gana_la_regla_mas_restrictiva(self):
        ajustes = Ajustes(reglas=[Regla("git", "permitir"), Regla("push --force", "denegar")])
        regla = regla_aplicable(ajustes.reglas, _contexto(comando="git push --force"))
        self.assertEqual(regla.decision, "denegar")

    def test_las_reglas_permisivas_estan_apagadas_por_defecto(self):
        ajustes = Ajustes(reglas=[Regla("cat ", "permitir")])
        self.assertIs(decidir(ajustes, 1, _contexto(comando="cat notas.txt")).decision,
                      Decision.PREGUNTAR)
        ajustes.reglas_permisivas = True
        self.assertIs(decidir(ajustes, 1, _contexto(comando="cat notas.txt")).decision,
                      Decision.PERMITIR)

    def test_una_regla_puede_limitarse_a_un_agente(self):
        ajustes = Ajustes(reglas=[Regla("npm", "denegar", agente="claude")])
        self.assertIs(decidir(ajustes, 0, _contexto(comando="npm install")).decision,
                      Decision.PERMITIR)
        contexto = _contexto(agente="claude", comando="npm install")
        self.assertIs(decidir(ajustes, 0, contexto).decision, Decision.DENEGAR)

    def test_los_patrones_vacios_no_coinciden_con_todo(self):
        ajustes = Ajustes(reglas=[Regla("   ", "denegar")])
        self.assertIsNone(regla_aplicable(ajustes.reglas, _contexto(comando="ls")))

    def test_un_contexto_sin_datos_no_dispara_reglas(self):
        self.assertIsNone(regla_aplicable(Ajustes().reglas, _contexto()))


class PruebaModosForzados(unittest.TestCase):
    def test_siempre_preguntar(self):
        ajustes = Ajustes(modo_aprobacion="siempre_preguntar")
        self.assertIs(decidir(ajustes, 0, _contexto()).decision, Decision.PREGUNTAR)

    def test_siempre_permitir(self):
        ajustes = Ajustes(modo_aprobacion="siempre_permitir")
        self.assertIs(decidir(ajustes, None, _contexto(), conectado=False).decision,
                      Decision.PERMITIR)


if __name__ == "__main__":
    unittest.main()
