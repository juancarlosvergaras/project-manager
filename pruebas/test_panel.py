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
                self.assertTrue(any(a["id"] == "codex" for a in datos["agentes"]))
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
