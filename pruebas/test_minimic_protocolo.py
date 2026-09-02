"""Pruebas del protocolo del MiniMic, contra los bytes capturados al programa del fabricante."""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada  # noqa: F401  (fija sys.path)
from minimic import protocolo
from minimic.protocolo import Atajo


def sin_ceros(p: bytes) -> str:
    """Los bytes útiles del paquete más la suma de control, para comparar a ojo."""
    fin = 5 + p[4]
    return p[:fin].hex(" ") + " … " + f"{p[63]:02x}"


class PruebaPaquetes(unittest.TestCase):
    def test_escribir_tecla_reproduce_la_captura(self):
        # Capturado: tecla 3 (índice 2) de la capa 1 puesta a «x»; el último byte es 0x13.
        p = protocolo.escribir_tecla(0, 2, Atajo.desde_texto("x").a_registro())
        self.assertEqual(len(p), 64)
        self.assertEqual(sin_ceros(p), "03 01 00 02 0a 00 00 00 00 00 00 00 01 00 1b … 13")

    def test_combinacion_reproduce_la_captura(self):
        # Capturado: alt+retroceso -> 0c 04 00 00 00 00 00 00 03 00 04 01 2a, suma 0x27.
        p = protocolo.escribir_tecla(0, 2, Atajo.desde_texto("alt-retroceso").a_registro())
        self.assertEqual(sin_ceros(p), "03 01 00 02 0c 04 00 00 00 00 00 00 03 00 04 01 2a … 27")

    def test_lecturas_y_ajustes(self):
        self.assertEqual(sin_ceros(protocolo.informacion()), "03 0c 00 00 00 … 0c")
        self.assertEqual(sin_ceros(protocolo.leer_capa(0)), "03 04 00 ff 00 … fb")
        self.assertEqual(sin_ceros(protocolo.leer_ajustes()), "03 0d 00 01 01 01 … 0c")
        self.assertEqual(sin_ceros(protocolo.escribir_ajustes(1)), "03 0e 00 01 03 01 01 01 … 0d")

    def test_rechaza_capas_y_teclas_fuera_de_rango(self):
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.leer_capa(3)
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.escribir_tecla(0, 5, b"")
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.escribir_ajustes(2)


class PruebaRegistros(unittest.TestCase):
    def test_decodifica_lo_que_traia_de_fabrica(self):
        casos = {
            "04 00 00 00 00 00 00 03 00 01 01 04": "ctrl-a",
            "04 00 00 00 00 00 00 03 00 01 01 19": "ctrl-v",
            "00 00 00 00 00 00 00 01 00 2a": "retroceso",
            "00 00 00 00 00 00 00 01 00 28": "intro",
            "04 00 00 00 00 00 00 02 00 09 00": "ctrl-win",
        }
        for crudo, texto in casos.items():
            with self.subTest(texto):
                self.assertEqual(str(Atajo.desde_registro(bytes.fromhex(crudo))), texto)

    def test_ida_y_vuelta(self):
        for texto in ("x", "ctrl-a", "ctrl-win", "ctrl-mayus-alt-f13", "win-h", "f24", "nada"):
            with self.subTest(texto):
                atajo = Atajo.desde_texto(texto)
                self.assertEqual(Atajo.desde_registro(atajo.a_registro()), atajo)
                self.assertEqual(str(atajo), texto)

    def test_alias_en_ingles_y_codigos_a_mano(self):
        self.assertEqual(str(Atajo.desde_texto("Ctrl-Shift-Enter")), "ctrl-mayus-intro")
        self.assertEqual(Atajo.desde_texto("<0x68>").codigos, (0x68,))
        with self.assertRaises(protocolo.ErrorProtocolo):
            Atajo.desde_texto("ctrl-loquesea")

    def test_solo_modificadores_es_combinacion_sin_teclas(self):
        registro = Atajo.desde_texto("ctrl-win").a_registro()
        self.assertEqual(registro.hex(" "), "04 00 00 00 00 00 00 02 00 09 00")


class PruebaRespuestas(unittest.TestCase):
    def test_acuse_y_rechazo(self):
        acuse = protocolo.analizar(bytes.fromhex("03 06 00 00 02 00 00 00 04") + bytes(55))
        self.assertTrue(acuse.es_acuse)
        rechazo = protocolo.analizar(bytes.fromhex("03 07 01 fd fe") + bytes(59))
        self.assertTrue(rechazo.es_rechazo)

    def test_registro_de_tecla_leido(self):
        r = protocolo.analizar(bytes.fromhex("03 03 00 04 0b 04 00 00 00 00 00 00 02 00 09 00") + bytes(48))
        self.assertEqual((r.orden, r.capa, r.arg), (protocolo.ORDEN_REGISTRO_DE_TECLA, 0, 4))
        self.assertEqual(str(Atajo.desde_registro(r.carga)), "ctrl-win")

    def test_ajustes(self):
        r = protocolo.analizar(bytes.fromhex("03 0d 00 01 03 01 01 00") + bytes(56))
        self.assertEqual(protocolo.Ajustes.desde_carga(r.carga).modo_microfono, protocolo.MICROFONO_MANTENER)

    def test_informe_ajeno(self):
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.analizar(b"\x01\x02")


if __name__ == "__main__":
    unittest.main()
