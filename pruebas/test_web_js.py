"""Los guiones de los paneles no llevan saltos de línea reales dentro de cadenas.

No hay Node en las máquinas de pruebas para analizar JavaScript de verdad, así
que se hace lo tosco que basta para el fallo que ya pasó: un ``\\n`` que la
consola convirtió en salto real dentro de ``"…"`` dejó ``app.js`` con un error
de sintaxis y los paneles mudos en «Esperando…». Una línea con un número
impar de comillas fuera de comentarios, cadenas y expresiones regulares es
sospechosa; las plantillas (`` ` ``) sí pueden abarcar varias líneas y se
ignoran.
"""

from __future__ import annotations

import re
import unittest

from pruebas.base import RAIZ

#: Una expresión regular literal: /…/ tras un paréntesis, coma, igual o espacio.
_REGEX = re.compile(r"(?<=[(=,:\s])/(?:[^/\\\n]|\\.)+/[a-z]*")
#: Una cadena entera en una sola línea, con comillas dobles o simples.
_CADENA = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')


class PruebaGuiones(unittest.TestCase):
    def test_sin_saltos_dentro_de_cadenas(self):
        sospechosas = []
        for guion in sorted((RAIZ / "src").glob("*/web/*.js")):
            texto = guion.read_text(encoding="utf-8")
            en_plantilla = False
            for numero, linea in enumerate(texto.splitlines(), 1):
                limpia = _REGEX.sub("", linea)
                limpia = _CADENA.sub("", limpia)
                limpia = re.sub(r"//.*$", "", limpia)
                if limpia.count("`") % 2:
                    en_plantilla = not en_plantilla
                    continue
                if en_plantilla:
                    continue
                if limpia.count('"') % 2 or limpia.count("'") % 2:
                    sospechosas.append(f"{guion.relative_to(RAIZ)}:{numero}: {linea.strip()[:80]}")
        self.assertEqual(sospechosas, [], "\n".join(sospechosas))

    def test_caza_el_fallo_que_ya_paso(self):
        """La línea rota de hoy tiene que saltar; la arreglada, no."""
        rota = 'pre.textContent = r.lineas.join("'
        buena = 'pre.textContent = r.lineas.join("\\n") : `Sin registro`;'
        regex = 'return String(t ?? "").replace(/[&<>"\']/g, (c) =>'
        limpia = lambda l: re.sub(r"//.*$", "", _CADENA.sub("", _REGEX.sub("", l)))  # noqa: E731
        self.assertEqual(limpia(rota).count('"') % 2, 1)
        self.assertEqual(limpia(buena).count('"') % 2, 0)
        self.assertEqual((limpia(regex).count('"') % 2, limpia(regex).count("'") % 2), (0, 0))


if __name__ == "__main__":
    unittest.main()
