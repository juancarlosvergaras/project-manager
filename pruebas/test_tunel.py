"""El túnel al portero, de punta a punta y en local.

Se levanta el portero de verdad (``despliegue/sikaimini/portero.py``, cargado
por ruta porque no es un paquete), un panel fingido, y un ``Tunel`` que se
presenta. Un «navegador» entra por el portero y tiene que llegar al panel
fingido, y el panel tiene que ver que la conexión NO viene de ``127.0.0.1``:
de eso depende que se pida la clave.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import unittest
from pathlib import Path

from pruebas.base import RAIZ  # noqa: F401  (fija sys.path)
from minimic.tunel import Tunel, analizar_portero, se_puede_usar_el_origen


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cargar_portero(puerto_web: int, puerto_agentes: int, destinos: str = ""):
    os.environ["PORTERO_PUERTO"] = str(puerto_web)
    os.environ["PORTERO_AGENTES_IP"] = "127.0.0.1"
    os.environ["PORTERO_AGENTES_PUERTO"] = str(puerto_agentes)
    os.environ["PORTERO_PCS"] = destinos or "127.0.0.1:1"  # nadie
    ruta = RAIZ / "despliegue" / "sikaimini" / "portero.py"
    espec = importlib.util.spec_from_file_location("portero_sikaimini", ruta)
    modulo = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(modulo)  # type: ignore[union-attr]
    return modulo


class PruebaTunel(unittest.TestCase):
    def test_analizar_portero(self):
        self.assertEqual(analizar_portero("100.65.52.65:8027"), ("100.65.52.65", 8027))
        self.assertEqual(analizar_portero("100.65.52.65"), ("100.65.52.65", 8027))
        self.assertIsNone(analizar_portero(""))
        self.assertIsNone(analizar_portero("100.65.52.65:ocho"))

    @unittest.skipUnless(se_puede_usar_el_origen(), "este sistema no deja salir desde 127.0.0.2")
    def test_navegador_llega_al_panel_por_el_tunel_y_no_parece_local(self):
        puerto_web, puerto_agentes, puerto_panel = puerto_libre(), puerto_libre(), puerto_libre()
        portero = cargar_portero(puerto_web, puerto_agentes)
        visto: dict = {}

        async def panel_fingido(lector, escritor):
            visto["origen"] = escritor.get_extra_info("peername")[0]
            peticion = await lector.readuntil(b"\r\n\r\n")
            visto["peticion"] = peticion.decode()
            cuerpo = b'{"app": "sikaimini", "hola": true}'
            escritor.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(cuerpo) + cuerpo)
            await escritor.drain()
            escritor.close()

        async def caso():
            panel = await asyncio.start_server(panel_fingido, "127.0.0.1", puerto_panel)
            web = await asyncio.start_server(portero.atender, "127.0.0.1", puerto_web)
            agentes = await asyncio.start_server(portero.atender_agente, "127.0.0.1", puerto_agentes)
            tunel = Tunel("sikaimini", puerto_panel, ("127.0.0.1", puerto_agentes), lambda: {"equipo": "pc-prueba", "teclado": True})
            tarea = asyncio.ensure_future(tunel.mantener())
            try:
                for _ in range(50):
                    if tunel.conectado and portero.agente_elegido() is not None:
                        break
                    await asyncio.sleep(0.05)
                self.assertTrue(tunel.conectado)
                self.assertEqual(portero.agente_elegido().equipo, "pc-prueba")
                self.assertTrue(portero.agente_elegido().teclado)

                lector, escritor = await asyncio.open_connection("127.0.0.1", puerto_web)
                escritor.write(b"GET /api/salud HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                await escritor.drain()
                respuesta = await asyncio.wait_for(lector.read(), 5)
                escritor.close()
                self.assertIn(b'"hola": true', respuesta)
                self.assertTrue(visto["peticion"].startswith("GET /api/salud"))
                self.assertEqual(visto["origen"], "127.0.0.2", "el panel debe ver que no es local")

                tunel.parar()
                tarea.cancel()
                await asyncio.sleep(0.1)
                # Sin agente y sin PC de respaldo: la página de cortesía.
                portero.AGENTES.clear()
                lector, escritor = await asyncio.open_connection("127.0.0.1", puerto_web)
                escritor.write(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
                await escritor.drain()
                respuesta = await asyncio.wait_for(lector.read(), 10)
                escritor.close()
                self.assertTrue(respuesta.startswith(b"HTTP/1.1 503"))
            finally:
                tunel.parar()
                tarea.cancel()
                for s in (panel, web, agentes):
                    s.close()
                    await s.wait_closed()

        asyncio.run(caso())


class PruebaServicioConTunel(unittest.TestCase):
    def test_sin_clave_no_se_presenta(self):
        from sikaimini.config import Ajustes
        from sikaimini.servicio import Servicio
        from pruebas.test_sikaimini_servicio import TecladoFingido
        from sikaimini import dispositivo

        async def caso():
            servicio = Servicio(Ajustes(), dispositivo.Teclado(TecladoFingido().abrir))
            servicio.bucle = asyncio.get_running_loop()
            servicio.asegurar_tunel()
            self.assertIn("clave", servicio.motivo_sin_tunel)
            self.assertFalse(servicio.resumen()["tunel"]["conectado"])
            servicio.ajustes.usar_portero = False
            servicio.ajustes.clave_panel = "secreta1"
            servicio.asegurar_tunel()
            self.assertIn("apagado", servicio.motivo_sin_tunel)

        asyncio.run(caso())


if __name__ == "__main__":
    unittest.main()
