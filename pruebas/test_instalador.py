"""Pruebas de la instalación de enganches: no debe pisar nada ajeno."""

from __future__ import annotations

import json
import unittest

from pruebas.base import PruebaAislada
from tecladoia import instalador
from tecladoia.agentes.claude import AgenteClaude
from tecladoia.agentes.codex import AgenteCodex
from tecladoia.agentes.gemini import AgenteGemini


class PruebaInstalacion(PruebaAislada):
    def test_instala_en_todos_los_agentes_conocidos(self):
        resultado = instalador.instalar()
        self.assertEqual(len(resultado), 5)  # el genérico no se instala
        for fila in instalador.revisar():
            if fila["id"] != "generico":
                self.assertTrue(fila["instalado"], fila["nombre"])

    def test_respeta_los_enganches_que_ya_existian(self):
        ruta = AgenteClaude.ruta_config()
        ruta.parent.mkdir(parents=True)
        ruta.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "Bash", "hooks": [{"type": "command", "command": "mio.sh"}]}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        instalador.instalar(["claude"])
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        ordenes = [
            h["command"]
            for grupo in datos["hooks"]["PreToolUse"]
            for h in grupo["hooks"]
        ]
        self.assertIn("mio.sh", ordenes)
        self.assertEqual(datos["model"], "opus")
        self.assertTrue(any("tecladoia" in o for o in ordenes))

    def test_al_desinstalar_solo_se_va_lo_nuestro(self):
        ruta = AgenteClaude.ruta_config()
        ruta.parent.mkdir(parents=True)
        ruta.write_text(
            json.dumps(
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mio.sh"}]}]}}
            ),
            encoding="utf-8",
        )
        instalador.instalar(["claude"])
        instalador.desinstalar(["claude"])
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        ordenes = [h["command"] for g in datos["hooks"]["Stop"] for h in g["hooks"]]
        self.assertEqual(ordenes, ["mio.sh"])
        self.assertFalse(AgenteClaude.instalado())

    def test_instalar_dos_veces_no_duplica_entradas(self):
        instalador.instalar(["claude"])
        instalador.instalar(["claude"])
        datos = json.loads(AgenteClaude.ruta_config().read_text(encoding="utf-8"))
        nuestras = [
            h
            for grupo in datos["hooks"]["PreToolUse"]
            for h in grupo["hooks"]
            if "tecladoia" in h["command"]
        ]
        self.assertEqual(len(nuestras), 1)

    def test_guarda_copia_de_seguridad_antes_de_tocar_un_fichero(self):
        ruta = AgenteClaude.ruta_config()
        ruta.parent.mkdir(parents=True)
        ruta.write_text('{"model": "opus"}', encoding="utf-8")
        instalador.instalar(["claude"])
        copias = list(ruta.parent.glob("settings.json.*.respaldo"))
        self.assertEqual(len(copias), 1)
        self.assertIn("opus", copias[0].read_text(encoding="utf-8"))

    def test_codex_activa_la_funcion_de_enganches(self):
        instalador.instalar(["codex"])
        toml = AgenteCodex.ruta_toml().read_text(encoding="utf-8")
        self.assertIn("[features]", toml)
        self.assertIn("hooks = true", toml)

    def test_codex_no_repite_la_funcion_si_ya_estaba(self):
        ruta = AgenteCodex.ruta_toml()
        ruta.parent.mkdir(parents=True)
        ruta.write_text("[features]\nhooks = true\n", encoding="utf-8")
        instalador.instalar(["codex"])
        self.assertEqual(ruta.read_text(encoding="utf-8").count("hooks = true"), 1)

    def test_gemini_usa_milisegundos_en_el_tiempo_limite(self):
        instalador.instalar(["gemini"])
        datos = json.loads(AgenteGemini.ruta_config().read_text(encoding="utf-8"))
        entrada = datos["hooks"]["BeforeTool"][0]["hooks"][0]
        self.assertEqual(entrada["timeout"], 20000)

    def test_agente_desconocido(self):
        with self.assertRaises(ValueError):
            instalador.instalar(["noexiste"])


if __name__ == "__main__":
    unittest.main()
