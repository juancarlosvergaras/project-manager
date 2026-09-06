"""Servicio, configuración y panel de la Botonera con un teclado fingido que, como el real, no contesta."""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from pathlib import Path

from pruebas.base import PruebaAislada
from botonera import dispositivo, protocolo
from botonera.config import COLORES_INICIALES, PERILLAS_INICIALES, TECLAS_INICIALES, Ajustes, Perfil
from botonera.panel import PanelWeb
from botonera.servicio import Servicio


class CanalFingido:
    """La interfaz de fabricante: traga informes de 65 bytes y no dice nada."""

    def __init__(self) -> None:
        self.escritos: list[bytes] = []
        self.aperturas = 0

    def abrir(self) -> "CanalFingido":
        self.aperturas += 1
        return self

    def escribir(self, datos: bytes) -> None:
        assert len(datos) == 65 and datos[0] == 3, datos
        self.escritos.append(datos)

    def cerrar(self) -> None:
        pass

    def ordenes(self) -> list[str]:
        return [d[1:3].hex(" ") for d in self.escritos]


def presente() -> dispositivo.Presencia:
    return dispositivo.Presencia(cable=True, ruta=b"x", serie="CD70")


class PruebaServicio(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["BOTONERA_INICIO"] = str(self.casa / "botonera")
        self.canal = CanalFingido()
        self.ajustes = Ajustes()
        self.servicio = Servicio(self.ajustes, dispositivo.Teclado(self.canal.abrir))
        self.servicio.teclado.escribir = lambda mensajes, pausa_s=0: dispositivo.Teclado.escribir(self.servicio.teclado, mensajes, 0)  # type: ignore[method-assign]
        self.servicio.estado.presencia = presente()

    def test_aplicar_graba_los_tres_perfiles_enteros(self):
        r = self.servicio.aplicar()
        self.assertTrue(r["escrito"])
        self.assertEqual(r["mensajes"], 3 * (21 * 2 + 1))
        self.assertEqual(len(self.canal.escritos), 129)
        # la primera orden es la tecla 1 del perfil 1 con F13; la última, las luces del perfil 3
        self.assertEqual(self.canal.escritos[0][:10].hex(" "), "03 fd 01 01 01 00 01 00 00 68")
        self.assertEqual(self.canal.escritos[-1][:8].hex(" "), "03 fe b0 02 01 dc 26 26")
        guardados = Ajustes.cargar()
        self.assertTrue(guardados.ultima_escritura)
        self.assertEqual(guardados.serie_del_teclado, "CD70")

    def test_poner_pieza_graba_solo_esa_y_la_guarda(self):
        r = self.servicio.poner_pieza(1, 5, "Ctrl-C")
        self.assertEqual((r["escrito"], r["accion"]), (True, "ctrl-c"))
        self.assertEqual(len(self.canal.escritos), 2)
        self.assertEqual(self.canal.escritos[0][:5].hex(" "), "03 fd 06 02 01")
        self.assertEqual(Ajustes.cargar().perfil(1).teclas[5], "ctrl-c")
        r = self.servicio.poner_pieza(0, 13, "rueda-arriba")  # perilla 1, pulsación
        self.assertEqual(Ajustes.cargar().perfil(0).perillas[0][1], "rueda-arriba")
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_pieza(0, 0, "loquesea")
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_pieza(3, 0, "a")

    def test_sin_cable_se_guarda_y_no_se_escribe(self):
        self.servicio.estado.presencia = dispositivo.Presencia(bluetooth=True)
        r = self.servicio.poner_pieza(0, 0, "esc")
        self.assertFalse(r["escrito"])
        self.assertEqual(self.canal.escritos, [])
        self.assertEqual(Ajustes.cargar().perfil(0).teclas[0], "esc")
        self.assertFalse(self.servicio.aplicar()["escrito"])
        self.servicio.estado.presencia = dispositivo.Presencia(otro_jieli=True)
        self.assertIn("otro", self.servicio.poner_luces(0, 1, "#ffffff")["aviso"])

    def test_luces_probar_no_guarda_y_guardar_si(self):
        r = self.servicio.poner_luces(2, 3, "#00FF00", solo_probar=True)
        self.assertTrue(r["escrito"] and r["probado"])
        self.assertEqual(self.canal.escritos[-1][:8].hex(" "), "03 fe b0 02 03 00 ff 00")
        self.assertEqual(Ajustes.cargar().perfil(2).luces_color, COLORES_INICIALES[2])
        r = self.servicio.poner_luces(2, 0, "#00ff00")
        self.assertEqual(Ajustes.cargar().perfil(2).luces_modo, 0)
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_luces(0, 1, "verde")

    def test_poner_perfil_cambia_y_graba_entero(self):
        r = self.servicio.poner_perfil(0, {"nombre": "Claude", "teclas": ["ctrl-mayus-alt-f13"] + ["nada"] * 11, "luces_color": "#112233"})
        self.assertTrue(r["escrito"])
        self.assertEqual(r["mensajes"], 43)
        p = Ajustes.cargar().perfil(0)
        self.assertEqual((p.nombre, p.teclas[0], p.teclas[1], p.luces_color), ("Claude", "ctrl-mayus-alt-f13", "nada", "#112233"))
        with self.assertRaises(ValueError):
            self.servicio.poner_perfil(0, {"teclas": ["a"]})
        with self.assertRaises(protocolo.ErrorProtocolo):
            self.servicio.poner_perfil(0, {"teclas": ["loquesea"] * 12})

    def test_restablecer(self):
        self.servicio.poner_pieza(0, 0, "esc")
        self.canal.escritos.clear()
        r = self.servicio.restablecer(0)
        self.assertTrue(r["escrito"])
        self.assertEqual(Ajustes.cargar().perfil(0).teclas, list(TECLAS_INICIALES))
        self.assertEqual(len(self.canal.escritos), 43)

    def test_al_conectar_graba_si_esta_encendido(self):
        self.servicio.ajustes.escribir_al_conectar = True
        import botonera.servicio as s
        dormir, s.time.sleep = s.time.sleep, lambda _: None
        try:
            self.servicio._al_cambiar_presencia(presente())
        finally:
            s.time.sleep = dormir
        self.assertEqual(len(self.canal.escritos), 129)
        self.canal.escritos.clear()
        self.servicio.ajustes.escribir_al_conectar = False
        s.time.sleep = lambda _: None
        try:
            self.servicio._al_cambiar_presencia(presente())
        finally:
            s.time.sleep = dormir
        self.assertEqual(self.canal.escritos, [])

    def test_sin_clave_no_se_presenta_al_portero(self):
        async def caso():
            self.servicio.bucle = asyncio.get_running_loop()
            self.servicio.asegurar_tunel()
            self.assertIn("clave", self.servicio.motivo_sin_tunel)
            self.assertFalse(self.servicio.resumen()["tunel"]["conectado"])
            self.servicio.ajustes.usar_portero = False
            self.servicio.ajustes.clave_panel = "secreta1"
            self.servicio.asegurar_tunel()
            self.assertIn("apagado", self.servicio.motivo_sin_tunel)
        asyncio.run(caso())

    def test_resumen(self):
        r = self.servicio.resumen()
        self.assertEqual(len(r["perfiles"]), 3)
        self.assertEqual(r["perfiles"][0]["perillas"], [list(p) for p in PERILLAS_INICIALES])
        self.assertEqual(len(r["piezas"]), 21)
        self.assertEqual(r["conexion"]["descripcion"], "por cable")


class PruebaPanel(PruebaAislada):
    PUERTO = 8797

    def setUp(self) -> None:
        super().setUp()
        os.environ["BOTONERA_INICIO"] = str(self.casa / "botonera")
        self.canal = CanalFingido()

    def correr(self, caso, clave: str = ""):
        async def dentro():
            ajustes = Ajustes(puerto_panel=self.PUERTO, host_panel="127.0.0.1", clave_panel=clave)
            servicio = Servicio(ajustes, dispositivo.Teclado(self.canal.abrir))
            servicio.bucle = asyncio.get_running_loop()
            servicio.estado.presencia = presente()
            panel = PanelWeb(servicio, ajustes)
            panel.confiar_en_local = False
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

    def test_estado_pieza_luces_y_aplicar(self):
        async def caso(panel, servicio):
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(len(json.loads(cuerpo)["perfiles"]), 3)
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/pieza", {"perfil": 0, "pieza": 3, "accion": "win-h"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"), cuerpo)
            self.assertEqual(json.loads(cuerpo)["accion"], "win-h")
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/pieza", {"perfil": 0, "pieza": 3, "accion": "loquesea"})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/pieza", {"perfil": 7, "pieza": 3, "accion": "a"})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/luces", {"perfil": 1, "modo": 2, "color": "#0000ff"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"), cuerpo)
            self.assertEqual(json.loads(cuerpo)["luces"]["color"], "#0000ff")
            estado, _, _ = await self.pedir(panel.puerto, "POST", "/api/luces", {"perfil": 1, "modo": "uno", "color": "#0000ff"})
            self.assertTrue(estado.startswith("HTTP/1.1 400"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/aplicar", {})
            self.assertEqual(json.loads(cuerpo)["mensajes"], 129)
            estado, _, cuerpo = await self.pedir(panel.puerto, "POST", "/api/perfil", {"perfil": 2, "nombre": "Libre"})
            self.assertEqual(json.loads(cuerpo)["perfil"]["nombre"], "Libre")
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/opciones")
            o = json.loads(cuerpo)
            self.assertIn("rueda-abajo", o["raton"])
            self.assertEqual(o["atajos_de_dictado"][0]["accion"], "ctrl-mayus-alt-f13")
        self.correr(caso)

    def test_clave_por_cabecera_cookie_y_salud_libre(self):
        async def caso(panel, servicio):
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 401"))
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado", cabeceras={"X-Botonera-Clave": "secreta1"})
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            estado, cabeza, _ = await self.pedir(panel.puerto, "GET", "/?clave=secreta1")
            self.assertTrue(estado.startswith("HTTP/1.1 303"))
            self.assertIn("Set-Cookie: botonera=secreta1", cabeza)
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/api/salud")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertEqual(json.loads(cuerpo)["app"], "botonera")
        self.correr(caso, clave="secreta1")

    def test_desde_el_propio_equipo_no_se_pide_clave_y_estaticos(self):
        async def caso(panel, servicio):
            panel.confiar_en_local = True
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/api/estado")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            estado, _, cuerpo = await self.pedir(panel.puerto, "GET", "/")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            self.assertIn(b"Botonera", cuerpo)
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/app.js")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))
            estado, _, _ = await self.pedir(panel.puerto, "GET", "/../config.py")
            self.assertTrue(estado.startswith("HTTP/1.1 200"))  # se queda en index.html
        self.correr(caso, clave="secreta1")


class PruebaConfig(PruebaAislada):
    def setUp(self) -> None:
        super().setUp()
        os.environ["BOTONERA_INICIO"] = str(self.casa / "botonera")

    def test_roto_o_raro_vuelve_a_lo_inicial(self):
        ruta = Path(os.environ["BOTONERA_INICIO"]) / "config.json"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{no es json", encoding="utf-8")
        self.assertEqual(Ajustes.cargar().puerto_panel, 8773)
        ruta.write_text(json.dumps({"perfiles": [{"teclas": ["a"], "luces_modo": 999, "luces_color": "azul", "nombre": "Uno"}], "escribir_al_conectar": "sí"}), encoding="utf-8")
        a = Ajustes.cargar()
        self.assertEqual(len(a.perfiles), 3)
        p = a.perfil(0)
        self.assertEqual((p.nombre, p.teclas, p.luces_modo, p.luces_color), ("Uno", list(TECLAS_INICIALES), 1, COLORES_INICIALES[0]))
        self.assertTrue(a.escribir_al_conectar)

    def test_guardar_y_cargar(self):
        a = Ajustes(clave_panel="secreta1")
        perfil = a.perfil(1)
        perfil.teclas[0] = "Ctrl-Mayus-Esc"
        a.guardar_perfil(1, perfil)
        a.guardar()
        b = Ajustes.cargar()
        self.assertEqual(b.perfil(1).teclas[0], "ctrl-mayus-esc")
        self.assertIs(b.como_dict()["clave_panel"], True)
        self.assertEqual(Perfil.inicial(2).luces_color, COLORES_INICIALES[2])


if __name__ == "__main__":
    unittest.main()
