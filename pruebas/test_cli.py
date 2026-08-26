"""Pruebas de la línea de órdenes."""

from __future__ import annotations

import contextlib
import io
import unittest

from pruebas.base import PruebaAislada
from tecladoia.cli import construir_analizador, main
from tecladoia.config import Ajustes


class PruebaAnalizador(unittest.TestCase):
    def test_todas_las_ordenes_estan_registradas(self):
        analizador = construir_analizador()
        esperadas = {
            "servicio", "estado", "buscar", "palanca", "instalar", "desinstalar",
            "agentes", "enganche", "tecla", "luz", "bitacora", "config", "probar",
        }
        registradas = set()
        for accion in analizador._subparsers._group_actions:  # noqa: SLF001
            registradas.update(accion.choices)
        self.assertEqual(esperadas, registradas)

    def test_sin_orden_es_un_error(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            construir_analizador().parse_args([])


class PruebaOrdenes(PruebaAislada):
    def _correr(self, argumentos) -> tuple[int, str]:
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
            codigo = main(argumentos)
        return codigo, salida.getvalue()

    def test_la_demo_recorre_los_dos_estados_de_la_palanca(self):
        codigo, texto = self._correr(["--sin-color", "probar"])
        self.assertEqual(codigo, 0)
        self.assertIn("MANUAL", texto)
        self.assertIn("AUTOMÁTICO", texto)
        self.assertIn("denegar", texto)  # la regla de rm -rf sigue mandando

    def test_config_muestra_las_rutas_y_las_reglas(self):
        codigo, texto = self._correr(["--sin-color", "config"])
        self.assertEqual(codigo, 0)
        self.assertIn("config.json", texto)
        self.assertIn("rm -rf", texto)

    def test_config_crear_escribe_el_fichero(self):
        codigo, _ = self._correr(["--sin-color", "config", "--crear"])
        self.assertEqual(codigo, 0)
        self.assertTrue((self.casa / "datos" / "config.json").exists())

    def test_instalar_y_listar_agentes(self):
        self._correr(["--sin-color", "instalar", "claude"])
        codigo, texto = self._correr(["--sin-color", "agentes"])
        self.assertEqual(codigo, 0)
        self.assertIn("Claude Code", texto)
        self.assertIn("Gemini CLI", texto)

    def test_la_bitacora_vacia_lo_dice(self):
        codigo, texto = self._correr(["--sin-color", "bitacora"])
        self.assertEqual(codigo, 0)
        self.assertIn("vacía", texto)

    def test_palanca_sin_servicio_avisa(self):
        # Un puerto donde no escucha nadie, para no toparse con un servicio
        # que esta misma máquina pueda tener en marcha de verdad.
        Ajustes(puerto_hooks=1).guardar()
        codigo, _ = self._correr(["--sin-color", "palanca", "auto"])
        self.assertEqual(codigo, 1)

    def test_palanca_con_un_modo_invalido(self):
        codigo, _ = self._correr(["--sin-color", "palanca", "loquesea"])
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
