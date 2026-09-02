"""Pruebas de la elección del cuadro de escribir (sin Windows: con cuadros fingidos)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from pruebas.base import PruebaAislada  # noqa: F401  (fija sys.path)
from tecladoia.cuadro_de_texto import elegir_cuadro


def cuadro(nombre: str, abajo: int) -> SimpleNamespace:
    return SimpleNamespace(CurrentName=nombre, CurrentBoundingRectangle=SimpleNamespace(bottom=abajo))


class PruebaElegirCuadro(unittest.TestCase):
    def test_sin_nombres_gana_el_de_mas_abajo(self):
        elegido = elegir_cuadro([cuadro("", 100), cuadro("", 900), cuadro("", 500)])
        self.assertEqual(elegido.CurrentBoundingRectangle.bottom, 900)

    def test_la_terminal_pierde_aunque_este_mas_abajo(self):
        # Lo que pasó con la terminal de Claude abierta: «Terminal input» quedaba
        # debajo del «Prompt» y se dictaba en la terminal.
        elegido = elegir_cuadro([cuadro("Prompt", 700), cuadro("Terminal input", 1000)])
        self.assertEqual(elegido.CurrentName, "Prompt")

    def test_el_chat_gana_a_un_cuadro_sin_nombre_mas_bajo(self):
        elegido = elegir_cuadro([cuadro("Prompt", 700), cuadro("", 1000)])
        self.assertEqual(elegido.CurrentName, "Prompt")

    def test_entre_dos_terminales_el_de_mas_abajo(self):
        elegido = elegir_cuadro([cuadro("Terminal input", 300), cuadro("Console", 800)])
        self.assertEqual(elegido.CurrentName, "Console")

    def test_ignora_mayusculas_y_nombre_nulo(self):
        elegido = elegir_cuadro([cuadro(None, 900), cuadro("MESSAGE", 100)])
        self.assertEqual(elegido.CurrentName, "MESSAGE")


if __name__ == "__main__":
    unittest.main()
