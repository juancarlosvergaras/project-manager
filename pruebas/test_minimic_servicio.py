"""Pruebas del servicio y del panel de MiniMic con un teclado fingido.

El teclado fingido contesta como el de verdad, byte a byte, incluidos los
acuses sin longitud (``03 06 00 00 ff …``) que despistaron la primera vez.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from pathlib import Path

from pruebas.base import PruebaAislada
from minimic import dispositivo, protocolo
from minimic.config import ATAJO_MICROFONO, TECLAS_DE_FABRICA, Ajustes
from minimic.panel import PanelWeb
from minimic.protocolo import Atajo
from minimic.servicio import Servicio


class TecladoFingido:
    """Firmware en memoria: guarda el mapa y los ajustes, y contesta como el real."""

    def __init__(self) -> None:
        self.teclas = {i: Atajo.desde_texto(t) for i, t in enumerate(TECLAS_DE_FABRICA)}
        self.modo_microfono = protocolo.MICROFONO_MANTENER
        self.escritos: list[bytes] = []
        self.aperturas = 0

    def abrir(self) -> "TecladoFingido":
        self.aperturas += 1
        self._cola: list[bytes] = []
        return self

    # -- lo que ve el Teclado --
    def escribir(self, datos: bytes) -> None:
        assert len(datos) == 64 and datos[0] == 3
        assert datos[63] == protocolo.suma_de_control(datos), "sin suma de control el teclado rechaza"
        self.escritos.append(datos)
        orden, capa, arg, n = datos[1], datos[2], datos[3], datos[4]
        carga = datos[5:5 + n]
        if orden == protocolo.ORDEN_INFORMACION:
            self._cola.append(self._informe(0x0C, 0, 0, bytes.fromhex("a501080001000000")))
        elif orden == protocolo.ORDEN_LEER_AJUSTES:
            self._cola.append(self._informe(0x0D, 0, 1, bytes([1, 1, self.modo_microfono])))
        elif orden == protocolo.ORDEN_ESCRIBIR_AJUSTES:
            self.modo_microfono = carga[2]
            self._cola.append(self._acuse(1))
        elif orden == protocolo.ORDEN_LEER_CAPA:
            for i, a in sorted(self.teclas.items()):
                r = a.a_registro()
                self._cola.append(self._informe(0x03, capa, i, r))
            self._cola.append(self._acuse(0xFF))
        elif orden == protocolo.ORDEN_ESCRIBIR_TECLA:
            self.teclas[arg] = Atajo.desde_registro(carga)
            self._cola.append(self._acuse(arg))
        else:
            self._cola.append(bytes([3, 7, 1, datos[2], datos[3], 0, 0, 0, datos[2] ^ datos[3] ^ 6]) + bytes(55))

    def leer(self, plazo_s: float) -> bytes | None:
        return self._cola.pop(0) if self._cola else None

    def cerrar(self) -> None:
        pass

    @staticmethod
    def _informe(orden: int, capa: int, arg: int, carga: bytes) -> bytes:
        p = bytearray(64); p[0], p[1], p[2], p[3], p[4] = 3, orden, capa, arg, len(carga); p[5:5 + len(carga)] = carga
        return bytes(p)

    @staticmethod
    def _acuse(eco: int) -> bytes:
        return bytes([3, 6, 0, 0, eco, 0, 0, 0, 6 ^ eco]) + bytes(55)


class PruebaTeclado(unittest.TestCase):
    def setUp(self) -> None:
        self.fingido = TecladoFingido()
        self.teclado = dispositivo.Teclado(self.fingido.abrir)

    def test_lee_el_mapa_de_fabrica(self):
        mapa = self.teclado.leer_capa(0)
        self.assertEqual(mapa.como_texto(), {0: "ctrl-a", 1: "ctrl-v", 2: "retroceso", 3: "intro", 4: "ctrl-win"})
        self.assertEqual(self.teclado.ajustes().modo_microfono, protocolo.MICROFONO_MANTENER)

    def test_escribe_y_relee(self):
        self.teclado.escribir_tecla(0, 4, Atajo.desde_texto(ATAJO_MICROFONO))
        self.teclado.modo_microfono(protocolo.MICROFONO_PULSAR)
        self.assertEqual(self.teclado.leer_capa(0).como_texto()[4], ATAJO_MICROFONO)
        self.assertEqual(self.teclado.ajustes().modo_microfono, protocolo.MICROFONO_PULSAR)

    def test_cada_conversacion_abre_y_cierra_el_canal(self):
        self.teclado.leer_capa(0)
        self.teclado.ajustes()
        self.assertEqual(self.fingido.aperturas, 2)

    def test_rechazo_se_convierte_en_error(self):
        class Rechazador(TecladoFingido):
            def escribir(self, datos):
                self._cola.append(bytes([3, 7, 1, 0, 0, 0, 0, 0, 6]) + bytes(55))
        teclado = dispositivo.Teclado(Rechazador().abrir)
        with self.assertRaises(dispositivo.ErrorDispositivo):
            teclado.escribir_tecla(0, 0, Atajo.desde_texto("a"))


class PruebaServicio(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["MINIMIC_INICIO"] = str(self.casa / "minimic")
        self.fingido = TecladoFingido()
        self.ajustes = Ajustes()
        self.servicio = Servicio(self.ajustes, dispositivo.Teclado(self.fingido.abrir))
        self.servicio.estado.presencia = dispositivo.Presencia(cable=True, receptor=False, ruta_configuracion=b"x")

    def test_asegurar_escribe_solo_lo_que_difiere(self):
        self.servicio.asegurar_teclado()
        escritos = [d[1] for d in self.fingido.escritos]
        # una lectura de capa, una de ajustes, la tecla 5 y el modo del micrófono
        self.assertEqual(escritos.count(protocolo.ORDEN_ESCRIBIR_TECLA), 1)
        self.assertEqual(escritos.count(protocolo.ORDEN_ESCRIBIR_AJUSTES), 1)
        self.assertEqual(str(self.fingido.teclas[4]), ATAJO_MICROFONO)
        self.assertEqual(self.fingido.modo_microfono, protocolo.MICROFONO_PULSAR)
        self.assertEqual(self.servicio.estado.mapa[4], ATAJO_MICROFONO)
        self.assertEqual(Ajustes.cargar().ultimo_mapa, self.servicio.estado.mapa)

    def test_segunda_pasada_no_escribe_nada(self):
        self.servicio.asegurar_teclado()
        self.fingido.escritos.clear()
        self.servicio.asegurar_teclado()
        self.assertNotIn(protocolo.ORDEN_ESCRIBIR_TECLA, [d[1] for d in self.fingido.escritos])

    def test_poner_teclas_valida_y_escribe(self):
        r = self.servicio.poner_teclas(["ctrl-c", "ctrl-v", "retroceso", "intro", ATAJO_MICROFONO])
        self.assertTrue(r["escrito"])
        self.assertEqual(str(self.fingido.teclas[0]), "ctrl-c")
        with self.assertRaises(ValueError):
            self.servicio.poner_teclas(["a"])
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_teclas(["a", "b", "c", "d", "loquesea"])

    def test_sin_cable_se_guarda_y_no_se_escribe(self):
        self.servicio.estado.presencia = dispositivo.Presencia(cable=False, receptor=True)
        r = self.servicio.poner_teclas(list(TECLAS_DE_FABRICA))
        self.assertFalse(r["escrito"])
        self.assertEqual(self.fingido.escritos, [])
        self.assertEqual(Ajustes.cargar().teclas, list(TECLAS_DE_FABRICA))

    def test_resumen_sin_teclado_ensena_el_ultimo_mapa(self):
        self.servicio.asegurar_teclado()
        self.servicio.estado.mapa = []
        self.servicio.estado.presencia = dispositivo.Presencia()
        resumen = self.servicio.resumen()
        self.assertEqual(resumen["mapa"][4], ATAJO_MICROFONO)
        self.assertFalse(resumen["mapa_es_reciente"])
        self.assertEqual(resumen["conexion"]["descripcion"], "no está")


class PruebaPanel(PruebaAislada):
    PUERTO = 8791

    def setUp(self) -> None:
        super().setUp()
        os.environ["MINIMIC_INICIO"] = str(self.casa / "minimic")
        self.fingido = TecladoFingido()

    def correr(self, caso, clave: str = "", host: str = "127.0.0.1"):
        async def dentro():
            ajustes = Ajustes(puerto_panel=self.PUERTO, host_panel=host, clave_panel=clave)
            servicio = Servicio(ajustes, dispositivo.Teclado(self.fingido.abrir))
            servicio.bucle = asyncio.get_running_loop()
            servicio.estado.presencia = dispositivo.Presencia(cable=True, receptor=False, ruta_configuracion=b"x")
            panel = PanelWeb(servicio, ajustes)
            await panel.arrancar()
            try:
                return await caso(panel, servicio)
            finally:
                await panel.detener()
        return asyncio.run(dentro())

    async def pedir(self, puerto: int, metodo: str, ruta: str, cuerpo: dict | None = None, cabeceras: dict | None = None):
        lector, escritor = await asyncio.open_connection("127.0.0.1", puerto)
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else b""
        lineas = [f"{metodo} {ruta} HTTP/1.1", "Host: local", f"Content-Length: {len(datos)}"]
        lineas += [f"{k}: {v}" for k, v in (cabeceras or {}).items()]
        escritor.write(("\r\n".join(lineas) + "\r\n\r\n").encode() + datos)
        await escritor.drain()
        crudo = await lector.read()
        escritor.close()
        cabeza, _, resto = crudo.partition(b"\r\n\r\n")
        estado = cabeza.split(b"\r\n")[0].decode()
        return estado, cabeza.decode("latin-1"), resto

    def test_estado_y_teclas_por_http(self):
        async def caso(panel, servicio):
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(json.loads(cuerpo)["conexion"]["descripcion"], "por cable")
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/teclas", {"teclas": ["ctrl-c", "ctrl-v", "retroceso", "intro", ATAJO_MICROFONO]})
            self.assertTrue(estado.startswith("HTTP/1.1 200"), cuerpo)
            self.assertEqual(str(self.fingido.teclas[0]), "ctrl-c")
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/teclas", {"teclas": ["x"]})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/microfono", {"modo": 0})
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(self.fingido.modo_microfono, 0)
        self.correr(caso)

    def test_clave_por_cabecera_cookie_y_salud_libre(self):
        async def caso(panel, servicio):
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 401"))
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado", cabeceras={"X-MiniMic-Clave": "secreta1"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            estado, cabeza, _ = await self.pedir(panel.puerto, "GET", "/?clave=secreta1")
            self.assertTrue(estado.startswith("HTTP/1.1 303"))
            self.assertIn("Set-Cookie: minimic=secreta1", cabeza)
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado", cabeceras={"Cookie": "minimic=secreta1"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/salud")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(json.loads(cuerpo)["app"], "minimic")
        self.correr(caso, clave="secreta1")

    def test_fuera_de_local_sin_clave_no_abre(self):
        async def caso(panel, servicio):
            self.assertIsNone(panel.puerto)
        self.correr(caso, host="0.0.0.0")

    def test_estaticos_sin_salir_de_la_carpeta(self):
        async def caso(panel, servicio):
            estado, cabeza, cuerpo = await self.pedir(panel.puerto, "GET", "/")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertIn(b"MiniMic", cuerpo)
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/../pyproject.toml")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))  # cae a index.html
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/noexiste.txt")
            self.assertTrue(estado.startswith("HTTP/1.1 404"))
        self.correr(caso)

    def test_ajustes_validan(self):
        async def caso(panel, servicio):
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/ajustes", {"programa": "marciano"})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/ajustes", {"programa": "chatgpt", "alto_cuadro": 140})
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(Ajustes.cargar().programa, "chatgpt")
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/ajustes")
            self.assertEqual(json.loads(cuerpo)["alto_cuadro"], 140)
            self.assertIs(json.loads(cuerpo)["clave_panel"], False)
        self.correr(caso)


class PruebaProgramaActivo(unittest.TestCase):
    def test_sigue_a_la_ventana_conocida(self):
        a = Ajustes(programa="activo")
        self.assertEqual(a.programa_elegido("ChatGPT")["id"], "chatgpt")
        self.assertEqual(a.programa_elegido("claude.exe")["id"], "claude")
        self.assertEqual(a.programa_elegido("Cursor")["id"], "cursor")

    def test_ventana_desconocida_dicta_donde_este_el_cursor(self):
        a = Ajustes(programa="activo")
        self.assertEqual(a.programa_elegido("chrome")["proceso"], "")
        self.assertEqual(a.programa_elegido("")["proceso"], "")

    def test_programa_fijo_no_mira_la_ventana(self):
        a = Ajustes(programa="claude")
        self.assertEqual(a.programa_elegido("ChatGPT")["id"], "claude")


class PruebaConfig(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["MINIMIC_INICIO"] = str(self.casa / "minimic")

    def test_roto_o_raro_vuelve_a_fabrica(self):
        ruta = Path(os.environ["MINIMIC_INICIO"]) / "config.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{no es json", encoding="utf-8")
        self.assertEqual(Ajustes.cargar().puerto_panel, 8771)
        ruta.write_text(json.dumps({"puerto_panel": "ocho", "teclas": ["a"], "modo_microfono": 7, "programa": "cursor", "desconocido": 1}), encoding="utf-8")
        a = Ajustes.cargar()
        self.assertEqual(a.puerto_panel, 8771)
        self.assertEqual(a.teclas[4], ATAJO_MICROFONO)
        self.assertEqual(a.modo_microfono, protocolo.MICROFONO_PULSAR)
        self.assertEqual(a.programa, "cursor")

    def test_guardar_y_cargar(self):
        a = Ajustes(clave_panel="secreta1", alto_cuadro=90)
        a.guardar()
        b = Ajustes.cargar()
        self.assertEqual((b.clave_panel, b.alto_cuadro), ("secreta1", 90))
        self.assertIs(b.como_dict()["clave_panel"], True)


if __name__ == "__main__":
    unittest.main()
