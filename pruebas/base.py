"""Utilidades comunes de las pruebas: aíslan HOME y la carpeta de trabajo."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))


class PruebaAislada(unittest.TestCase):
    """Cada prueba corre con su propio HOME y su propia carpeta de datos."""

    def setUp(self) -> None:
        self.temporal = tempfile.TemporaryDirectory()
        self.casa = Path(self.temporal.name)
        self._entorno_previo = {
            clave: os.environ.get(clave)
            for clave in ("HOME", "USERPROFILE", "APPDATA", "TECLADOIA_INICIO", "TECLADOIA_SOCKET")
        }
        os.environ["HOME"] = str(self.casa)
        os.environ["USERPROFILE"] = str(self.casa)
        os.environ["APPDATA"] = str(self.casa / "AppData")
        os.environ["TECLADOIA_INICIO"] = str(self.casa / "datos")
        os.environ["TECLADOIA_SOCKET"] = str(self.casa / "tecladoia.sock")
        self.addCleanup(self._restaurar)

    def _restaurar(self) -> None:
        for clave, valor in self._entorno_previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        self.temporal.cleanup()
