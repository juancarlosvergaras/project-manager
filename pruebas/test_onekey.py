"""OneKey: configuración, servicio y panel, sin botón de verdad."""

from __future__ import annotations

import asyncio
import json
import os
import unittest

from pruebas.base import PruebaAislada
from minimic import boton
from onekey.config import Ajustes, ruta_config
from onekey.panel import PanelWeb
from onekey.servicio import Servicio


class PruebaConfig(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["ONEKEY_INICIO"] = str(self.casa / "onekey")

    def test_de_fabrica_busca_el_ai_voice_y_envia_al_cerrar(self):
        a = Ajustes()
        self.assertEqual(a.boton_bluetooth, "AI_VOICE")
        self.assertTrue(a.enviar_al_cerrar)
        self.assertEqual(a.puerto_panel, 8774)
        self.assertEqual(a.portero, "100.65.52.65:8033")

    def test_guarda_y_carga_sin_devolver_la_clave(self):
        a = Ajustes(clave_panel="secreta1", boton_bluetooth="Mi boton", programa="claude")
        a.guardar()
        self.assertTrue(ruta_config().exists())
        b = Ajustes.cargar()
        self.assertEqual(b.clave_panel, "secreta1")
        self.assertEqual(b.boton_bluetooth, "Mi boton")
        self.assertEqual(b.programa, "claude")
        self.assertIs(b.como_dict()["clave_panel"], True)

    def test_lo_raro_del_disco_se_ignora(self):
        ruta_config().parent.mkdir(parents=True, exist_ok=True)
        ruta_config().write_text(json.dumps({"puerto_panel": "ocho", "boton_bluetooth": 5, "desconocido": 1, "adoptar_microfono": False}), encoding="utf-8")
        a = Ajustes.cargar()
        self.assertEqual(a.puerto_panel, 8774)
        self.assertEqual(a.boton_bluetooth, "AI_VOICE")
        self.assertFalse(a.adoptar_microfono)


class PruebaServicio(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["ONEKEY_INICIO"] = str(self.casa / "onekey")

    def test_resumen_sin_boton(self):
        s = Servicio(Ajustes())
        r = s.resumen()
        self.assertEqual(r["boton"]["nombre"], "AI_VOICE")
        self.assertTrue(r["boton"]["buscado"])
        self.assertFalse(r["boton"]["conectado"])
        self.assertEqual(r["dictado"]["atajo"], "ctrl+alt+may+f17")
        self.assertFalse(r["tunel"]["conectado"])

    def test_resumen_con_boton(self):
        s = Servicio(Ajustes())
        s.estado.boton = boton.Boton("AI_VOICE", "5BCBA23EA614", "{X}", ["ruta"])
        s.estado.microfono = "AI_VOICE Hands-Free"
        s.estado.microfono_es_el_del_sistema = True
        r = s.resumen()
        self.assertTrue(r["boton"]["conectado"])
        self.assertEqual(r["boton"]["direccion"], "5BCBA23EA614")
        self.assertEqual(r["microfono"]["nombre"], "AI_VOICE Hands-Free")
        self.assertEqual(s._presentacion()["teclado"], True)

    def test_sin_clave_no_se_presenta_al_portero(self):
        s = Servicio(Ajustes())
        s.bucle = asyncio.new_event_loop()
        try:
            s.asegurar_tunel()
            self.assertIn("clave", s.motivo_sin_tunel)
            self.assertIsNone(s._tunel)
        finally:
            s.bucle.close()


class PruebaPanel(PruebaAislada):
    PUERTO = 8794

    def setUp(self) -> None:
        super().setUp()
        os.environ["ONEKEY_INICIO"] = str(self.casa / "onekey")

    def correr(self, caso, clave: str = ""):
        async def dentro():
            ajustes = Ajustes(puerto_panel=self.PUERTO, clave_panel=clave)
            servicio = Servicio(ajustes)
            servicio.bucle = asyncio.get_running_loop()
            panel = PanelWeb(servicio, ajustes)
            panel.confiar_en_local = False
            await panel.arrancar()
            self.assertIsNotNone(panel.puerto)
            try:
                await caso(panel, servicio)
            finally:
                await panel.detener()
        asyncio.run(dentro())

    async def pedir(self, puerto, metodo, ruta, cuerpo=None, cabeceras=None):
        lector, escritor = await asyncio.open_connection("127.0.0.1", puerto)
        carga = json.dumps(cuerpo).encode() if cuerpo is not None else b""
        extra = "".join(f"{k}: {v}\r\n" for k, v in (cabeceras or {}).items())
        escritor.write(f"{metodo} {ruta} HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n{extra}Content-Length: {len(carga)}\r\n\r\n".encode() + carga)
        await escritor.drain()
        crudo = await asyncio.wait_for(lector.read(), 5)
        escritor.close()
        cabecera, _, resto = crudo.partition(b"\r\n\r\n")
        return cabecera.decode("latin-1").split("\r\n")[0], resto

    def test_salud_y_estado(self):
        async def caso(panel, servicio):
            estado, cuerpo = await self.pedir(panel.puerto, "GET", "/api/salud")
            self.assertIn("200", estado)
            datos = json.loads(cuerpo)
            self.assertEqual(datos["app"], "onekey")
            self.assertFalse(datos["teclado"])
            estado, cuerpo = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertIn("200", estado)
            self.assertEqual(json.loads(cuerpo)["boton"]["nombre"], "AI_VOICE")
            estado, cuerpo = await self.pedir(panel.puerto, "GET", "/")
            self.assertIn("200", estado)
            self.assertIn(b"OneKey", cuerpo)
        self.correr(caso)

    def test_con_clave_pide_clave_y_salud_no(self):
        async def caso(panel, servicio):
            estado, _ = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertIn("401", estado)
            estado, _ = await self.pedir(panel.puerto, "GET", "/api/salud")
            self.assertIn("200", estado)
            estado, _ = await self.pedir(panel.puerto, "GET", "/api/estado", cabeceras={"X-OneKey-Clave": "secreta1"})
            self.assertIn("200", estado)
        self.correr(caso, clave="secreta1")

    def test_cambiar_el_nombre_del_boton_desde_el_panel(self):
        async def caso(panel, servicio):
            estado, cuerpo = await self.pedir(panel.puerto, "POST", "/api/ajustes", {"boton_bluetooth": "  Otro  "})
            self.assertIn("200", estado)
            self.assertEqual(servicio.ajustes.boton_bluetooth, "Otro")
            self.assertEqual(servicio._nombre_del_boton(), "Otro")
            self.assertEqual(Ajustes.cargar().boton_bluetooth, "Otro")
            estado, _ = await self.pedir(panel.puerto, "POST", "/api/ajustes", {"boton_bluetooth": 7})
            self.assertIn("400", estado)
        self.correr(caso)
