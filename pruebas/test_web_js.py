"""Los guiones de los paneles no llevan saltos de línea reales dentro de cadenas.

No hay Node en las máquinas de pruebas para analizar JavaScript de verdad, así
que se hace lo tosco que basta para el fallo que ya pasó: un ``\\n`` que la
consola convirtió en salto real dentro de ``"…"`` dejó ``app.js`` con un error
de sintaxis y los paneles mudos en «Esperando…». Una línea con un número
impar de comillas fuera de comentarios es sospechosa; las plantillas
(`` ` ``) sí pueden abarcar varias líneas y se ignoran.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from pruebas.base import RAIZ

_CADENA = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')


class PruebaGuiones(unittest.TestCase):
    def test_sin_saltos_dentro_de_cadenas(self):
        sospechosas = []
        for guion in sorted((RAIZ / "src").glob("*/web/*.js")):
            texto = guion.read_text(encoding="utf-8")
            en_plantilla = False
            for numero, linea in enumerate(texto.splitlines(), 1):
                sin_cadenas = _CADENA.sub("", linea)
                sin_cadenas = re.sub(r"//.*$", "", sin_cadenas)
                if sin_cadenas.count("`") % 2:
                    en_plantilla = not en_plantilla
                    continue
                if en_plantilla:
                    continue
                if sin_cadenas.count('"') % 2 or sin_cadenas.count("'") % 2:
                    sospechosas.append(f"{guion.relative_to(RAIZ)}:{numero}: {linea.strip()[:80]}")
        self.assertEqual(sospechosas, [], "\n".join(sospechosas))


if __name__ == "__main__":
    unittest.main()
