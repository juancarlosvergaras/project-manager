"""Pruebas del panel web local."""

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


class PruebaPanel(PruebaAislada):
    async def _montar(self):
        ajustes = Ajustes(sincronizar_config_agentes=False, puerto_panel=8871, puerto_hooks=8941)
        simulado = TransporteSimulado(palanca=1)
        gestor = GestorTeclado(ajustes, simulado)
        await gestor.conectar()
        servidor = ServidorEnganches(gestor, ajustes)
        panel = PanelWeb(gestor, servidor, ajustes)
        panel.confiar_en_local = False  # las pruebas vienen de 127.0.0.1 y prueban la clave
        await panel.arrancar()
        return panel, gestor, simulado

    async def _pedir(self, panel, metodo, ruta, cuerpo=None):
        lector, escritor = await asyncio.open_connection("127.0.0.1", panel.puerto)
        carga = json.dumps(cuerpo).encode() if cuerpo is not None else b""
        peticion = (
            f"{metodo} {ruta} HTTP/1.1\r\nHost: localhost\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(carga)}\r\n\r\n"
        ).encode() + carga
        escritor.write(peticion)
        await escritor.drain()
        crudo = await asyncio.wait_for(lector.read(), 5)
        escritor.close()
        cabeceras, _, cuerpo_respuesta = crudo.partition(b"\r\n\r\n")
        return cabeceras.decode("latin-1"), cuerpo_respuesta

    def test_la_pagina_se_sirve_en_espanol(self):
        async def caso():
            panel, *_ = await self._montar()
            try:
                cabeceras, cuerpo = await self._pedir(panel, "GET", "/")
                self.assertIn("200 OK", cabeceras)
                texto = cuerpo.decode("utf-8")
                self.assertIn('<html lang="es">', texto)
                self.assertIn("Palanca de aprobación", texto)
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_el_estado_llega_como_json(self):
        async def caso():
            panel, *_ = await self._montar()
            try:
                _, cuerpo = await self._pedir(panel, "GET", "/api/estado")
                datos = json.loads(cuerpo)
                self.assertTrue(datos["estado"]["conectado"])
                self.assertEqual(datos["estado"]["palanca"], 1)
                self.assertTrue(any(a["id"] == "chatgpt" for a in datos["agentes"]))
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_la_palanca_virtual_se_puede_mover_desde_el_panel(self):
        async def caso():
            panel, gestor, _ = await self._montar()
            try:
                _, cuerpo = await self._pedir(panel, "POST", "/api/palanca", {"valor": 0})
                datos = json.loads(cuerpo)
                self.assertEqual(datos["estado"]["palanca"], 0)
                self.assertTrue(datos["estado"]["palanca_forzada"])

                await self._pedir(panel, "POST", "/api/palanca", {"valor": None})
                self.assertIsNone(gestor.palanca_forzada)
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_se_puede_cambiar_el_efecto_de_luz(self):
        async def caso():
            panel, _, simulado = await self._montar()
            try:
                _, cuerpo = await self._pedir(panel, "POST", "/api/luz", {"efecto": 5})
                self.assertTrue(json.loads(cuerpo)["ok"])
                self.assertEqual(simulado.modo_luz, 5)
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_una_ruta_inexistente_devuelve_404(self):
        async def caso():
            panel, *_ = await self._montar()
            try:
                cabeceras, _ = await self._pedir(panel, "GET", "/api/nada")
                self.assertIn("404", cabeceras)
            finally:
                await panel.detener()
        asyncio.run(caso())


if __name__ == "__main__":
    unittest.main()


class PruebaClaveDelPanel(PruebaAislada):
    """El panel mueve la palanca: expuesto sin clave sería un botón abierto."""

    async def _montar(self, **opciones):
        ajustes = Ajustes(
            sincronizar_config_agentes=False, puerto_panel=8881, puerto_hooks=8961, **opciones
        )
        simulado = TransporteSimulado(palanca=1)
        gestor = GestorTeclado(ajustes, simulado)
        await gestor.conectar()
        servidor = ServidorEnganches(gestor, ajustes)
        panel = PanelWeb(gestor, servidor, ajustes)
        panel.confiar_en_local = False  # las pruebas vienen de 127.0.0.1 y prueban la clave
        await panel.arrancar()
        return panel

    async def _pedir(self, panel, ruta, cabeceras=""):
        lector, escritor = await asyncio.open_connection("127.0.0.1", panel.puerto)
        escritor.write(
            f"GET {ruta} HTTP/1.1\r\nHost: localhost\r\n{cabeceras}\r\n".encode()
        )
        await escritor.drain()
        crudo = await asyncio.wait_for(lector.read(), 5)
        escritor.close()
        return crudo.decode("utf-8", "replace")

    def test_sin_clave_configurada_se_entra_directo(self):
        async def caso():
            panel = await self._montar()
            try:
                self.assertIn("200 OK", await self._pedir(panel, "/api/estado"))
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_con_clave_se_rechaza_a_quien_no_la_trae(self):
        async def caso():
            panel = await self._montar(clave_panel="secreta")
            try:
                respuesta = await self._pedir(panel, "/api/estado")
                self.assertIn("401", respuesta)
                self.assertIn("Hace falta la clave", respuesta)
                respuesta = await self._pedir(panel, "/api/estado?clave=otra")
                self.assertIn("401", respuesta)
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_la_clave_vale_por_consulta_cabecera_y_galleta(self):
        async def caso():
            panel = await self._montar(clave_panel="secreta")
            try:
                respuesta = await self._pedir(panel, "/?clave=secreta")
                # La primera visita guarda la clave y reenvía a la misma página
                # sin ella, para no dejarla escrita en la barra de direcciones
                # ni en el historial del navegador.
                self.assertIn("303 See Other", respuesta)
                self.assertIn("Set-Cookie: tecladoia=secreta", respuesta)
                self.assertIn("Location: /", respuesta)

                for cabecera in (
                    "Authorization: Bearer secreta\r\n",
                    "X-TecladoIA-Clave: secreta\r\n",
                    "Cookie: tecladoia=secreta\r\n",
                ):
                    with self.subTest(cabecera=cabecera):
                        self.assertIn(
                            "200 OK", await self._pedir(panel, "/api/estado", cabecera)
                        )
            finally:
                await panel.detener()
        asyncio.run(caso())

    def test_no_se_abre_al_exterior_sin_clave(self):
        async def caso():
            panel = await self._montar(host_panel="0.0.0.0")
            self.assertIsNone(panel.puerto)
            self.assertFalse(panel.solo_local)
            await panel.detener()
        asyncio.run(caso())

    def test_con_clave_si_se_abre_al_exterior(self):
        async def caso():
            panel = await self._montar(host_panel="0.0.0.0", clave_panel="secreta")
            try:
                self.assertIsNotNone(panel.puerto)
            finally:
                await panel.detener()
        asyncio.run(caso())
