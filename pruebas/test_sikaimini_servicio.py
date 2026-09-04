"""Pruebas del servicio y del panel de SikaiMini con un teclado fingido.

El fingido contesta como el de verdad: seis registros, luces de 52 bytes y
acuses sin longitud. Y hay un MiniMic fingido al lado, para comprobar que
ninguna de las dos aplicaciones le escribe al teclado de la otra.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from pathlib import Path

from pruebas.base import PruebaAislada
from sikaimini import dispositivo, protocolo
from sikaimini.config import ATAJO_MICROFONO, TECLAS_DE_FABRICA, TECLAS_DESEADAS, Ajustes
from sikaimini.panel import PanelWeb
from sikaimini.protocolo import Atajo, Luces
from sikaimini.servicio import Servicio

LUCES_DE_FABRICA = bytes.fromhex(
    "01 00 00 00 ff 00 00 00 ff 00 00 00 ff ff b4 00 ff 00 b4 00 b4 ff b4 ff 00 ff 50 50 50 ff 50 "
    "50 50 ff ff 78 ff 78 ff ff ff ff 78 ff 64 00 78 00 ff 00 ff b4"
)


class TecladoFingido:
    """Firmware en memoria con seis registros y luces."""

    def __init__(self, teclas: tuple[str, ...] = TECLAS_DE_FABRICA) -> None:
        self.teclas = {i: Atajo.desde_texto(t) for i, t in enumerate(teclas)}
        self.modo_microfono = protocolo.MICROFONO_MANTENER
        self.luces = bytearray(LUCES_DE_FABRICA)
        self.escritos: list[bytes] = []
        self.aperturas = 0

    def abrir(self) -> "TecladoFingido":
        self.aperturas += 1
        self._cola: list[bytes] = []
        return self

    def escribir(self, datos: bytes) -> None:
        assert len(datos) == 64 and datos[0] == 3
        assert datos[63] == protocolo.suma_de_control(datos)
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
        elif orden == protocolo.ORDEN_LEER_CAPA and capa == 0:
            for i, a in sorted(self.teclas.items()):
                self._cola.append(self._informe(0x03, capa, i, a.a_registro()))
            self._cola.append(self._acuse(0xFF))
        elif orden == protocolo.ORDEN_ESCRIBIR_TECLA and capa == 0 and arg in self.teclas:
            self.teclas[arg] = Atajo.desde_registro(carga)
            self._cola.append(self._acuse(arg))
        elif orden == protocolo.ORDEN_LEER_LUCES:
            self._cola.append(self._informe(0x0A, 0, 0xFE, bytes(self.luces)))
        elif orden == protocolo.ORDEN_ESCRIBIR_LUCES and arg == 0xFE and n == 52:
            self.luces = bytearray(carga)
            self._cola.append(self._acuse(0xFE))
        else:
            self._cola.append(bytes([3, 7, 2, datos[2], datos[3], 0, 0, 0, datos[2] ^ datos[3] ^ 7]) + bytes(55))

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

    def test_lee_lo_de_fabrica(self):
        mapa = self.teclado.leer_capa(0)
        self.assertEqual(list(mapa.como_texto().values()), list(TECLAS_DE_FABRICA))
        self.assertEqual(self.teclado.luces().modo, 1)

    def test_escribe_perilla_y_luces_y_relee(self):
        self.teclado.escribir_tecla(0, 3, Atajo.desde_texto("rueda-abajo"))
        self.teclado.poner_luces(self.teclado.luces().con(2, (0, 128, 255)))
        self.assertEqual(self.teclado.leer_capa(0).como_texto()[3], "rueda-abajo")
        self.assertEqual(self.teclado.luces().como_dict()["color"], "#0080ff")

    def test_sondear_devuelve_lo_que_conteste(self):
        r = self.teclado.sondear(protocolo.ORDEN_INFORMACION)
        self.assertEqual(r[0]["orden"], "0x0c")
        self.assertEqual(r[0]["carga"], "a5 01 08 00 01 00 00 00")
        r = self.teclado.sondear(0x0B, 0, 2, b"\x01")
        self.assertTrue(r[-1]["rechazo"])

    def test_un_minimic_no_es_este_teclado(self):
        from minimic.config import TECLAS_DE_FABRICA as MINIMIC
        minimic = TecladoFingido(MINIMIC)  # cinco registros
        teclado = dispositivo.Teclado(minimic.abrir)
        with self.assertRaises(dispositivo.ErrorDispositivo) as ctx:
            teclado.leer_capa(0)
        self.assertIn("MiniMic", str(ctx.exception))

    def test_y_minimic_tampoco_toma_a_este(self):
        from minimic import dispositivo as md
        teclado = md.Teclado(self.fingido.abrir)
        with self.assertRaises(md.ErrorDispositivo) as ctx:
            teclado.leer_capa(0)
        self.assertIn("SiKai", str(ctx.exception))


class PruebaServicio(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["SIKAIMINI_INICIO"] = str(self.casa / "sikaimini")
        self.fingido = TecladoFingido()
        self.ajustes = Ajustes()
        self.servicio = Servicio(self.ajustes, dispositivo.Teclado(self.fingido.abrir))
        self.servicio.estado.presencia = dispositivo.Presencia(cable=True, receptor=False, ruta_configuracion=b"x")

    def test_asegurar_deja_perilla_como_rueda_y_microfono_con_su_combinacion(self):
        self.servicio.asegurar_teclado()
        escritos = [d[1] for d in self.fingido.escritos]
        # la tecla del micrófono y los tres gestos de la perilla; No y Sí ya venían bien
        self.assertEqual(escritos.count(protocolo.ORDEN_ESCRIBIR_TECLA), 4)
        self.assertEqual(escritos.count(protocolo.ORDEN_ESCRIBIR_AJUSTES), 1)
        self.assertEqual(escritos.count(protocolo.ORDEN_ESCRIBIR_LUCES), 0)  # luces sin tocar de fábrica
        self.assertEqual([str(self.fingido.teclas[i]) for i in range(6)], list(TECLAS_DESEADAS))
        self.assertEqual(self.fingido.modo_microfono, protocolo.MICROFONO_PULSAR)
        self.assertEqual(self.servicio.estado.luces["modo"], 1)
        self.assertEqual(Ajustes.cargar().ultimo_mapa, self.servicio.estado.mapa)

    def test_segunda_pasada_no_escribe_nada(self):
        self.servicio.asegurar_teclado()
        self.fingido.escritos.clear()
        self.servicio.asegurar_teclado()
        self.assertNotIn(protocolo.ORDEN_ESCRIBIR_TECLA, [d[1] for d in self.fingido.escritos])
        self.assertNotIn(protocolo.ORDEN_ESCRIBIR_LUCES, [d[1] for d in self.fingido.escritos])

    def test_luces_elegidas_se_graban_al_conectar(self):
        r = self.servicio.poner_luces(1, "#00FF00")
        self.assertTrue(r["escrito"])
        self.assertEqual(self.fingido.luces[:4].hex(" "), "01 00 ff 00")
        self.assertEqual(self.fingido.luces[4:], LUCES_DE_FABRICA[4:])  # la paleta se respeta
        self.fingido.luces = bytearray(LUCES_DE_FABRICA)  # el teclado «olvida»
        self.servicio.asegurar_teclado()
        self.assertEqual(self.fingido.luces[:4].hex(" "), "01 00 ff 00")
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_luces(1, "verde")
        with self.assertRaises(ValueError):
            self.servicio.poner_luces(300, "#000000")

    def test_poner_piezas_valida_y_escribe(self):
        r = self.servicio.poner_teclas(["esc", "intro", ATAJO_MICROFONO, "rueda-abajo", "rueda-arriba", "silencio"])
        self.assertTrue(r["escrito"])
        self.assertEqual(str(self.fingido.teclas[0]), "esc")
        self.assertEqual(str(self.fingido.teclas[5]), "silencio")
        with self.assertRaises(ValueError):
            self.servicio.poner_teclas(["a"])
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_teclas(["a", "b", "c", "d", "e", "loquesea"])

    def test_sin_cable_se_guarda_y_no_se_escribe(self):
        self.servicio.estado.presencia = dispositivo.Presencia(cable=False, receptor=True)
        r = self.servicio.poner_teclas(list(TECLAS_DE_FABRICA))
        self.assertFalse(r["escrito"])
        self.assertEqual(self.fingido.escritos, [])
        self.assertEqual(Ajustes.cargar().teclas, list(TECLAS_DE_FABRICA))
        self.assertFalse(self.servicio.poner_luces(2, "#123456")["escrito"])

    def test_no_escribe_a_un_minimic(self):
        from minimic.config import TECLAS_DE_FABRICA as MINIMIC
        minimic = TecladoFingido(MINIMIC)
        servicio = Servicio(Ajustes(), dispositivo.Teclado(minimic.abrir))
        servicio.estado.presencia = dispositivo.Presencia(cable=True, receptor=False, ruta_configuracion=b"x")
        servicio.asegurar_teclado()
        self.assertNotIn(protocolo.ORDEN_ESCRIBIR_TECLA, [d[1] for d in minimic.escritos])
        self.assertTrue(servicio.estado.avisos and "MiniMic" in servicio.estado.avisos[0])


class PruebaPanel(PruebaAislada):
    PUERTO = 8793

    def setUp(self) -> None:
        super().setUp()
        os.environ["SIKAIMINI_INICIO"] = str(self.casa / "sikaimini")
        self.fingido = TecladoFingido()

    def correr(self, caso, clave: str = "", host: str = "127.0.0.1"):
        async def dentro():
            ajustes = Ajustes(puerto_panel=self.PUERTO, host_panel=host, clave_panel=clave)
            servicio = Servicio(ajustes, dispositivo.Teclado(self.fingido.abrir))
            servicio.bucle = asyncio.get_running_loop()
            servicio.estado.presencia = dispositivo.Presencia(cable=True, receptor=False, ruta_configuracion=b"x")
            panel = PanelWeb(servicio, ajustes)
            panel.confiar_en_local = False  # las pruebas vienen de 127.0.0.1 y quieren probar la clave
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
        return cabeza.split(b"\r\n")[0].decode(), cabeza.decode("latin-1"), resto

    def test_estado_teclas_y_luces_por_http(self):
        async def caso(panel, servicio):
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(len(json.loads(cuerpo)["piezas"]), 6)
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/teclas", {"teclas": ["esc", "intro", ATAJO_MICROFONO, "rueda-abajo", "rueda-arriba", "clic-central"]})
            self.assertTrue(estado.startswith("HTTP/1.1 200"), cuerpo)
            self.assertEqual(str(self.fingido.teclas[3]), "rueda-abajo")
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/teclas", {"teclas": ["x"]})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/luces", {"modo": 1, "color": "#0000ff"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"), cuerpo)
            self.assertEqual(json.loads(cuerpo)["luces"]["color"], "#0000ff")
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/luces", {"modo": "uno", "color": "#0000ff"})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/opciones")
            self.assertIn("rueda-abajo", json.loads(cuerpo)["raton"])
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/teclas/recomendado", {})
            self.assertEqual(str(self.fingido.teclas[5]), "clic-central")
        self.correr(caso)

    def test_clave_por_cabecera_cookie_y_salud_libre(self):
        async def caso(panel, servicio):
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 401"))
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado", cabeceras={"X-SikaiMini-Clave": "secreta1"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            estado, cabeza, _ = await self.pedir(panel.puerto, "GET", "/?clave=secreta1")
            self.assertTrue(estado.startswith("HTTP/1.1 303"))
            self.assertIn("Set-Cookie: sikaimini=secreta1", cabeza)
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/salud")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(json.loads(cuerpo)["app"], "sikaimini")
        self.correr(caso, clave="secreta1")

    def test_desde_el_propio_equipo_no_se_pide_clave(self):
        async def caso(panel, servicio):
            panel.confiar_en_local = True
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
        self.correr(caso, clave="secreta1")

    def test_estaticos(self):
        async def caso(panel, servicio):
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertIn(b"SiKai", cuerpo)
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/app.js")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
        self.correr(caso)


class PruebaConfig(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["SIKAIMINI_INICIO"] = str(self.casa / "sikaimini")

    def test_roto_o_raro_vuelve_a_fabrica(self):
        ruta = Path(os.environ["SIKAIMINI_INICIO"]) / "config.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{no es json", encoding="utf-8")
        self.assertEqual(Ajustes.cargar().puerto_panel, 8772)
        ruta.write_text(json.dumps({"teclas": ["a"], "luces_modo": 999, "luces_color": "azul", "programa": "cursor"}), encoding="utf-8")
        a = Ajustes.cargar()
        self.assertEqual(a.teclas, list(TECLAS_DESEADAS))
        self.assertEqual(a.luces_modo, -1)
        self.assertEqual(a.luces_color, "#ffffff")
        self.assertEqual(a.programa, "cursor")

    def test_guardar_y_cargar(self):
        a = Ajustes(clave_panel="secreta1", luces_modo=2, luces_color="#112233")
        a.guardar()
        b = Ajustes.cargar()
        self.assertEqual((b.clave_panel, b.luces_modo, b.luces_color), ("secreta1", 2, "#112233"))
        self.assertIs(b.como_dict()["clave_panel"], True)


if __name__ == "__main__":
    unittest.main()
