"""Pruebas del protocolo del SiKai mini, contra los bytes capturados el 4/9/2026."""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada  # noqa: F401  (fija sys.path)
from sikaimini import protocolo
from sikaimini.protocolo import Atajo, Luces


def sin_ceros(p: bytes) -> str:
    fin = 5 + p[4]
    return p[:fin].hex(" ") + " … " + f"{p[63]:02x}"


class PruebaPaquetes(unittest.TestCase):
    def test_rueda_arriba_reproduce_la_captura(self):
        # Capturado a LQ_Keyboard.exe al poner «Mouse Wheel+» en el giro A (índice 3); suma 0x09.
        p = protocolo.escribir_tecla(0, 3, Atajo.desde_texto("rueda-arriba").a_registro())
        self.assertEqual(sin_ceros(p), "03 01 00 03 0a 03 00 00 00 00 00 00 01 00 03 … 09")

    def test_solo_hay_una_capa_y_seis_piezas(self):
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.leer_capa(1)
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.escribir_tecla(0, 6, b"")
        self.assertEqual(sin_ceros(protocolo.leer_capa(0)), "03 04 00 ff 00 … fb")

    def test_luces_ida_y_vuelta(self):
        # Lo que trajo el teclado: modo 1, color negro y una paleta de 16 colores (52 bytes).
        carga = bytes.fromhex(
            "01 00 00 00 ff 00 00 00 ff 00 00 00 ff ff b4 00 ff 00 b4 00 b4 ff b4 ff 00 ff 50 50 50 ff 50 "
            "50 50 ff ff 78 ff 78 ff ff ff ff 78 ff 64 00 78 00 ff 00 ff b4"
        )
        luces = Luces.desde_carga(carga)
        self.assertEqual((luces.modo, luces.color), (1, (0, 0, 0)))
        self.assertEqual(len(luces.paleta), 16)
        self.assertEqual(luces.paleta[:2], ((0xFF, 0, 0), (0, 0xFF, 0)))
        self.assertEqual(luces.a_carga(), carga)
        rojas = luces.con(color=(255, 0, 0))
        p = protocolo.escribir_luces(rojas)
        self.assertEqual(p[1:5], bytes([0x09, 0, 0xFE, 52]))
        self.assertEqual(p[5:9].hex(" "), "01 ff 00 00")
        self.assertEqual(Luces.desde_carga(p[5:57]), rojas)

    def test_colores_en_texto(self):
        self.assertEqual(protocolo.color_desde_texto("#FF8000"), (255, 128, 0))
        self.assertEqual(protocolo.color_a_texto((255, 128, 0)), "#ff8000")
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.color_desde_texto("rojo")


class PruebaRegistros(unittest.TestCase):
    def test_decodifica_lo_que_traia_de_fabrica(self):
        casos = {
            "00 00 00 00 00 00 00 01 00 2a": "retroceso",
            "00 00 00 00 00 00 00 01 00 28": "intro",
            "04 00 00 00 00 00 00 02 00 09 00": "ctrl-win",
            "02 00 00 00 00 00 00 02 00 e9 00": "vol+",
            "02 00 00 00 00 00 00 02 00 ea 00": "vol-",
            "04 00 00 00 00 00 00 02 00 40 00": "ralt",
        }
        for crudo, texto in casos.items():
            with self.subTest(texto):
                self.assertEqual(str(Atajo.desde_registro(bytes.fromhex(crudo))), texto)

    def test_tabla_de_raton_capturada(self):
        # Cada botón de la pestaña «Mouse» del programa del fabricante, en su orden.
        esperado = ["clic", "clic-derecho", "clic-central", "rueda-arriba", "rueda-abajo", "ctrl-rueda-arriba",
                    "ctrl-rueda-abajo", "mayus-rueda-arriba", "mayus-rueda-abajo", "alt-rueda-arriba",
                    "alt-rueda-abajo", "gesto-izquierda", "gesto-derecha", "gesto-arriba", "gesto-abajo", "me-gusta"]
        for codigo, nombre in enumerate(esperado):
            registro = bytes([3, 0, 0, 0, 0, 0, 0, 1, 0, codigo])
            self.assertEqual(str(Atajo.desde_registro(registro)), nombre)
            self.assertEqual(Atajo.desde_texto(nombre).a_registro(), registro)

    def test_ida_y_vuelta(self):
        for texto in ("x", "ctrl-a", "ctrl-win", "ctrl-mayus-alt-f15", "vol+", "silencio", "calculadora",
                      "rueda-abajo", "clic-central", "nada", "raton<0x1f>", "multimedia<0x1a2>"):
            with self.subTest(texto):
                atajo = Atajo.desde_texto(texto)
                self.assertEqual(Atajo.desde_registro(atajo.a_registro()), atajo)
                self.assertEqual(str(atajo), texto)

    def test_multimedia_de_dos_bytes(self):
        self.assertEqual(Atajo.desde_texto("calculadora").a_registro().hex(" "), "02 00 00 00 00 00 00 02 00 92 01")

    def test_familias_y_alias(self):
        self.assertEqual(Atajo.desde_texto("rueda-abajo").familia, "raton")
        self.assertEqual(Atajo.desde_texto("vol+").familia, "multimedia")
        self.assertEqual(Atajo.desde_texto("ctrl-c").familia, "teclado")
        self.assertEqual(str(Atajo.desde_texto("wheel-down")), "rueda-abajo")
        with self.assertRaises(protocolo.ErrorProtocolo):
            Atajo.desde_texto("rueda-diagonal")


if __name__ == "__main__":
    unittest.main()
