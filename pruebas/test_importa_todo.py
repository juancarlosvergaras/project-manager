"""Todos los módulos de las tres aplicaciones tienen que importarse sin error.

Un error de sintaxis en un módulo que solo se importa al ejecutar el
instalador (``asistente``) no lo veía ninguna prueba, y el ejecutable llegó
roto al usuario: se abría y moría. Esta prueba importa cada módulo de
``src``; los que tocan Windows por dentro lo hacen al llamar, no al importar.
"""

from __future__ import annotations

import importlib
import pkgutil
import unittest

from pruebas.base import RAIZ  # noqa: F401  (fija sys.path)


class PruebaImportaTodo(unittest.TestCase):
    def test_todos_los_modulos_importan(self):
        fallos = []
        for paquete in ("tecladoia", "minimic", "sikaimini"):
            raiz = importlib.import_module(paquete)
            for info in pkgutil.walk_packages(raiz.__path__, paquete + "."):
                if info.name.endswith(".__main__"):
                    continue  # ejecuta la línea de órdenes al importarse
                try:
                    importlib.import_module(info.name)
                except Exception as error:  # noqa: BLE001
                    fallos.append(f"{info.name}: {error.__class__.__name__}: {error}")
        self.assertEqual(fallos, [], "\n".join(fallos))


if __name__ == "__main__":
    unittest.main()
