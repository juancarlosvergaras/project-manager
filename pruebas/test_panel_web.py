"""Pruebas de la aplicación web: rutas nuevas, clave de acceso y descarga."""

from __future__ import annotations

import asyncio
import json
import unittest

from pruebas.base import PruebaAislada
from tecladoia.config import Ajustes
from tecladoia.dispositivo import GestorTeclado
from tecladoia.panel import PanelWeb
from tecladoia.servidor import ServidorEnganches
from tecladoia.transporte.simulado import TransporteSimulado


class BasePanel(PruebaAislada):
    puerto_panel = 8881
    puerto_hooks = 8951

    async def montar(self, **extra):
        ajustes = Ajustes(
            sincronizar_config_agentes=False,
            puerto_panel=self.puerto_panel,
            puerto_hooks=self.puerto_hooks,
        )
        gestor = GestorTeclado(ajustes, TransporteSimulado(palanca=1))
        await gestor.conectar()
        servidor = ServidorEnganches(gestor, ajustes)
        for campo, valor in extra.items():
            setattr(ajustes, campo, valor)
        panel = PanelWeb(gestor, servidor, ajustes)
        panel.confiar_en_local = False  # las pruebas vienen de 127.0.0.1 y prueban la clave
        await panel.arrancar()
        return panel

    def correr(self, caso, **extra):
        """Monta el panel, ejecuta el caso y lo cierra en el mismo bucle.

        Cerrar un servidor de asyncio desde otro bucle distinto del que lo creó
        revienta en Windows, asi que todo vive y muere aqui dentro.
        """

        async def envoltura():
            panel = await self.montar(**extra)
            try:
                await caso(panel)
            finally:
                await panel.detener()

        asyncio.run(envoltura())

    async def pedir(self, panel, metodo, ruta, cuerpo=None, cabeceras=""):
        lector, escritor = await asyncio.open_connection("127.0.0.1", panel.puerto)
        carga = json.dumps(cuerpo).encode() if cuerpo is not None else b""
        peticion = (
            f"{metodo} {ruta} HTTP/1.1\r\nHost: localhost\r\n"
            f"Content-Type: application/json\r\n{cabeceras}"
            f"Content-Length: {len(carga)}\r\n\r\n"
        ).encode() + carga
        escritor.write(peticion)
        await escritor.drain()
        crudo = await asyncio.wait_for(lector.read(), 5)
        escritor.close()
        cabecera, _, cuerpo_resp = crudo.partition(b"\r\n\r\n")
        return cabecera.decode("latin-1"), cuerpo_resp

    async def json_de(self, panel, metodo, ruta, cuerpo=None):
        _, crudo = await self.pedir(panel, metodo, ruta, cuerpo)
        return json.loads(crudo)


class PruebaEstaticos(BasePanel):
    def test_la_pagina_y_sus_piezas_se_sirven(self):
        async def caso(panel):
            cabeceras, cuerpo = await self.pedir(panel, "GET", "/")
            self.assertIn("200 OK", cabeceras)
            self.assertIn('<html lang="es">', cuerpo.decode("utf-8"))

            for ruta, marca in (("/estilo.css", "text/css"), ("/app.js", "javascript")):
                cabeceras, cuerpo = await self.pedir(panel, "GET", ruta)
                self.assertIn("200 OK", cabeceras)
                self.assertIn(marca, cabeceras)
                self.assertTrue(cuerpo)

        self.correr(caso)

    def test_no_se_puede_salir_de_la_carpeta_web(self):
        async def caso(panel):
            cabeceras, cuerpo = await self.pedir(panel, "GET", "/../panel.py")
            # Se responde la propia página, nunca el código del servidor.
            self.assertNotIn("class PanelWeb", cuerpo.decode("utf-8", "replace"))
            self.assertIn("200 OK", cabeceras)

        self.correr(caso)


class PruebaReglas(BasePanel):
    puerto_panel = 8891
    puerto_hooks = 8961

    def test_se_leen_guardan_y_validan(self):
        async def caso(panel):
            datos = await self.json_de(panel, "GET", "/api/reglas")
            self.assertTrue(datos["reglas"])

            nuevas = {"reglas": [{"patron": "terraform destroy", "decision": "denegar"}]}
            guardadas = await self.json_de(panel, "POST", "/api/reglas", nuevas)
            self.assertEqual(len(guardadas["reglas"]), 1)
            self.assertEqual(guardadas["reglas"][0]["agente"], "*")
            self.assertEqual(len(Ajustes.cargar().reglas), 1)

            cabeceras, _ = await self.pedir(
                panel, "POST", "/api/reglas", {"reglas": [{"patron": "x", "decision": "quizas"}]}
            )
            self.assertIn("400", cabeceras)

        self.correr(caso)

    def test_el_probador_explica_la_decision(self):
        async def caso(panel):
            r = await self.json_de(
                panel,
                "POST",
                "/api/reglas/probar",
                {"herramienta": "Bash", "comando": "rm -rf /", "palanca": "0"},
            )
            self.assertEqual(r["decision"], "denegar")
            self.assertEqual(r["regla"]["patron"], "rm -rf")

            r = await self.json_de(
                panel, "POST", "/api/reglas/probar", {"comando": "ls", "palanca": "0"}
            )
            self.assertEqual(r["decision"], "permitir")

        self.correr(caso)


class PruebaTeclas(BasePanel):
    puerto_panel = 8901
    puerto_hooks = 8971

    def test_una_tecla_se_guarda_y_se_escribe(self):
        async def caso(panel):
            r = await self.json_de(
                panel,
                "POST",
                "/api/teclas",
                {"modo": 0, "indice": 2, "atajo": "ctrl+may+p", "descripcion": "Paleta"},
            )
            self.assertTrue(r["ok"])
            self.assertTrue(r["escrita_en_el_teclado"])
            self.assertEqual(r["modos"][0]["teclas"][2]["atajo"], "ctrl+may+p")
            self.assertEqual(Ajustes.cargar().modos[0].teclas[2].descripcion, "Paleta")

        self.correr(caso)

    def test_un_atajo_imposible_se_rechaza_con_su_motivo(self):
        async def caso(panel):
            cabeceras, cuerpo = await self.pedir(
                panel, "POST", "/api/teclas", {"modo": 0, "indice": 0, "atajo": "ctrl+xyzzy"}
            )
            self.assertIn("400", cabeceras)
            self.assertIn("xyzzy", json.loads(cuerpo)["error"])

        self.correr(caso)

    def test_atajo_y_macro_a_la_vez_no_tiene_sentido(self):
        async def caso(panel):
            cabeceras, _ = await self.pedir(
                panel,
                "POST",
                "/api/teclas",
                {"modo": 0, "indice": 0, "atajo": "ctrl+p", "texto_macro": "hola"},
            )
            self.assertIn("400", cabeceras)

        self.correr(caso)


class PruebaAjustesYBitacora(BasePanel):
    puerto_panel = 8911
    puerto_hooks = 8981

    def test_los_ajustes_se_guardan_con_su_tipo(self):
        async def caso(panel):
            r = await self.json_de(
                panel,
                "POST",
                "/api/ajustes",
                {"aprobacion_remota": True, "espera_aprobacion_s": 12, "brillo": 80},
            )
            self.assertIn("aprobacion_remota", r["cambios"])
            guardados = Ajustes.cargar()
            self.assertTrue(guardados.aprobacion_remota)
            self.assertEqual(guardados.brillo, 80)
            self.assertIsInstance(guardados.espera_aprobacion_s, float)

        self.correr(caso)

    def test_un_ajuste_desconocido_se_ignora(self):
        async def caso(panel):
            r = await self.json_de(panel, "POST", "/api/ajustes", {"borrar_todo": True})
            self.assertEqual(r["cambios"], [])

        self.correr(caso)

    def test_la_bitacora_sale_tambien_en_csv(self):
        async def caso(panel):
            await panel.servidor.procesar(
                json.dumps(
                    {
                        "orden": "evento",
                        "agente": "claude",
                        "evento": "PermissionRequest",
                        "contexto": {"herramienta": "Bash", "comando": "git status"},
                    }
                )
            )
            entradas = (await self.json_de(panel, "GET", "/api/bitacora"))["entradas"]
            self.assertTrue(entradas)

            cabeceras, cuerpo = await self.pedir(panel, "GET", "/api/bitacora.csv")
            self.assertIn("text/csv", cabeceras)
            self.assertIn("bitacora.csv", cabeceras)
            texto = cuerpo.decode("utf-8-sig")
            self.assertIn("instante,agente", texto)
            self.assertIn("git status", texto)

        self.correr(caso)


class PruebaDescarga(BasePanel):
    puerto_panel = 8921
    puerto_hooks = 8991

    def test_el_paquete_se_descarga_y_trae_la_aplicacion(self):
        async def caso(panel):
            import io
            import zipfile

            cabeceras, cuerpo = await self.pedir(panel, "GET", "/descargar/tecladoia.zip")
            self.assertIn("application/zip", cabeceras)
            self.assertIn("tecladoia.zip", cabeceras)
            with zipfile.ZipFile(io.BytesIO(cuerpo)) as paquete:
                nombres = paquete.namelist()
            self.assertIn("tecladoia/src/tecladoia/cli.py", nombres)
            self.assertIn("tecladoia/src/tecladoia/web/index.html", nombres)
            self.assertIn("tecladoia/INSTALAR.txt", nombres)
            self.assertFalse([n for n in nombres if "__pycache__" in n])

        self.correr(caso)


class PruebaClaveDeAcceso(BasePanel):
    puerto_panel = 8931
    puerto_hooks = 9001

    def test_sin_clave_no_se_entra_pero_se_ve_la_puerta(self):
        async def caso(panel):
            cabeceras, cuerpo = await self.pedir(panel, "GET", "/api/estado")
            self.assertIn("401", cabeceras)

            # La puerta se sirve con 401: es la respuesta honesta —no estás
            # autorizado— y aun así trae el formulario para que puedas entrar.
            cabeceras, cuerpo = await self.pedir(panel, "GET", "/")
            self.assertIn("401", cabeceras)
            self.assertIn("Clave del panel", cuerpo.decode("utf-8"))

        self.correr(caso, clave_panel="secreta")

    def test_con_la_clave_se_entra_por_cookie_o_por_cabecera(self):
        async def caso(panel):
            _, cuerpo = await self.pedir(
                panel, "GET", "/api/estado", cabeceras="Cookie: tecladoia=secreta\r\n"
            )
            self.assertTrue(json.loads(cuerpo)["estado"]["conectado"])

            _, cuerpo = await self.pedir(
                panel, "GET", "/api/estado", cabeceras="X-TecladoIA-Clave: secreta\r\n"
            )
            self.assertTrue(json.loads(cuerpo)["estado"]["conectado"])

            cabeceras, _ = await self.pedir(
                panel, "GET", "/api/estado", cabeceras="X-TecladoIA-Clave: otra\r\n"
            )
            self.assertIn("401", cabeceras)

        self.correr(caso, clave_panel="secreta")

    def test_entrar_deja_la_cookie_puesta(self):
        async def caso(panel):
            cabeceras, _ = await self.pedir(panel, "GET", "/?clave=secreta")
            self.assertIn("303 See Other", cabeceras)
            self.assertIn("Set-Cookie: tecladoia=secreta", cabeceras)
            self.assertIn("HttpOnly", cabeceras)
            # La clave no se queda escrita en la direccion.
            self.assertIn("Location: /", cabeceras)

            cabeceras, _ = await self.pedir(panel, "GET", "/?clave=mal")
            self.assertIn("401", cabeceras)

        self.correr(caso, clave_panel="secreta")

    def test_salir_a_la_red_sin_clave_se_rechaza(self):
        """La barrera que impide dejar el panel abierto sin querer."""

        async def caso_suelto():
            ajustes = Ajustes(
                sincronizar_config_agentes=False, puerto_panel=8941, puerto_hooks=9011
            )
            ajustes.host_panel = "0.0.0.0"
            ajustes.clave_panel = ""
            gestor = GestorTeclado(ajustes, TransporteSimulado())
            servidor = ServidorEnganches(gestor, ajustes)
            panel = PanelWeb(gestor, servidor, ajustes)
            panel.confiar_en_local = False  # las pruebas vienen de 127.0.0.1 y prueban la clave
            await panel.arrancar()
            # No se abre: sin clave, publicarlo seria dejar la palanca en manos
            # de cualquiera que alcance el equipo por la red.
            self.assertIsNone(panel.puerto)

        asyncio.run(caso_suelto())


if __name__ == "__main__":
    unittest.main()
