"""Pruebas de la tabla de teclas y de la distribución en español."""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada  # noqa: F401
from tecladoia import teclas
from tecladoia.protocolo import AccionMacro


class PruebaAtajos(unittest.TestCase):
    def test_los_modificadores_van_primero(self):
        self.assertEqual(teclas.atajo_a_codigos("p+ctrl+may"), [0xE0, 0xE1, 0x13])

    def test_nombres_en_espanol(self):
        self.assertEqual(teclas.atajo_a_codigos("ctrl+alt+supr"), [0xE0, 0xE2, 0x4C])
        self.assertEqual(teclas.atajo_a_codigos("may+intro"), [0xE1, 0x28])

    def test_f18_es_el_codigo_del_teclado(self):
        self.assertEqual(teclas.codigo_de("f18"), 0x6D)

    def test_no_se_repiten_los_modificadores(self):
        self.assertEqual(teclas.atajo_a_codigos("ctrl+control+c"), [0xE0, 0x06])

    def test_un_atajo_solo_de_modificadores_es_un_error(self):
        with self.assertRaises(teclas.ErrorTecla):
            teclas.atajo_a_codigos("ctrl+may")

    def test_tecla_desconocida(self):
        with self.assertRaises(teclas.ErrorTecla):
            teclas.codigo_de("tecla_que_no_existe")

    def test_descripcion_legible(self):
        self.assertEqual(teclas.describir([0xE0, 0x06]), "ctrl+c")


class PruebaDistribucionEspanola(unittest.TestCase):
    def test_la_enye_tiene_tecla_propia(self):
        self.assertEqual(teclas.codigo_de("ñ"), 0x33)

    def test_los_caracteres_del_espanol_estan_en_la_distribucion(self):
        for caracter in "ñÑ¿¡ç€@":
            with self.subTest(caracter=caracter):
                self.assertIn(caracter, teclas.DISTRIBUCION_ES)

    def test_una_macro_escribe_texto_con_tildes(self):
        pasos = teclas.texto_a_macro("Añ")
        acciones = [p[0] for p in pasos]
        self.assertIn(AccionMacro.PULSAR, acciones)
        self.assertIn(AccionMacro.SOLTAR_TODO, acciones)
        # «A» son dos pulsaciones (mayúscula + letra) y «ñ» una sola.
        self.assertEqual(acciones.count(AccionMacro.SOLTAR_TODO), 2)

    def test_una_macro_ignora_lo_que_no_sabe_escribir(self):
        self.assertEqual(teclas.texto_a_macro("😀"), [])


if __name__ == "__main__":
    unittest.main()


class PruebaObjetivoBLE(unittest.TestCase):
    """En Windows hay que entregarle a bleak un BLEDevice, no una cadena."""

    def test_fuera_de_windows_se_pasa_la_direccion_tal_cual(self):
        import os
        from unittest import mock

        from tecladoia.transporte.ble import TransporteBLE

        with mock.patch.object(os, "name", "posix"):
            self.assertEqual(
                TransporteBLE._objetivo("D4:6C:52:7C:C7:25", "AhaKey"),
                "D4:6C:52:7C:C7:25",
            )

    def test_en_windows_sin_bleak_se_cae_con_elegancia(self):
        """Sin bleak, el atajo se rinde y devuelve la dirección tal cual.

        La prueba simula de verdad que la biblioteca no está: antes daba por
        hecho que no estaba instalada, así que pasaba o fallaba según la máquina
        donde se corriera, que es justo lo que una prueba no debe hacer.
        """
        import builtins
        import os
        from unittest import mock

        from tecladoia.transporte.ble import TransporteBLE

        importar = builtins.__import__

        def sin_bleak(nombre, *resto):
            if nombre.startswith("bleak"):
                raise ImportError("bleak no está instalado")
            return importar(nombre, *resto)

        with mock.patch.object(os, "name", "nt"),              mock.patch.object(builtins, "__import__", sin_bleak):
            self.assertEqual(
                TransporteBLE._objetivo("D4:6C:52:7C:C7:25", ""), "D4:6C:52:7C:C7:25"
            )
