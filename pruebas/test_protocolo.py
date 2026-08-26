"""Pruebas del protocolo binario."""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada  # noqa: F401  (fija sys.path)
from tecladoia import protocolo


class PruebaTramas(unittest.TestCase):
    def test_construye_con_cabecera_y_cola(self):
        trama = protocolo.construir_trama(0x90, b"\x04")
        self.assertEqual(trama, bytes.fromhex("aabb9004ccdd"))

    def test_actualizar_estado_coincide_con_la_documentacion(self):
        self.assertEqual(protocolo.actualizar_estado(4).hex(), "aabb9004ccdd")

    def test_trama_invalida(self):
        self.assertFalse(protocolo.es_trama_valida(b"\x01\x02\x03"))
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.carga_util(b"\x01\x02\x03\x04\x05")

    def test_consulta_de_estado_del_ejemplo_capturado(self):
        # Captura documentada: batería 74 %, señal 50, firmware 1.0.
        trama = bytes.fromhex("aabb004a3201000000000000ccdd")
        estado = protocolo.analizar_estado(trama)
        self.assertIsNotNone(estado)
        self.assertEqual(estado.bateria, 74)
        self.assertEqual(estado.senal, 50)
        self.assertEqual(estado.firmware, "1.0")
        self.assertEqual(estado.palanca, 0)
        self.assertTrue(estado.aprobacion_automatica)

    def test_ignora_el_acuse_de_actualizar_estado(self):
        """El acuse de 0x90 no lleva la palanca: tomarlo por bueno la falsearía."""
        acuse = protocolo.construir_trama(protocolo.Comando.ACTUALIZAR_ESTADO, b"\x00")
        self.assertIsNone(protocolo.analizar_estado(acuse))

    def test_palanca_distinta_de_cero_no_aprueba_sola(self):
        trama = bytes.fromhex("aabb004a320100000001" + "00" + "ccdd")
        estado = protocolo.analizar_estado(trama)
        self.assertEqual(estado.palanca, 1)
        self.assertFalse(estado.aprobacion_automatica)

    def test_separar_tramas_reconstruye_notificaciones_partidas(self):
        memoria = bytearray()
        completa = protocolo.actualizar_estado(4)
        memoria.extend(b"\x00\x01")  # basura previa
        memoria.extend(completa[:3])
        self.assertEqual(protocolo.separar_tramas(memoria), [])
        memoria.extend(completa[3:])
        memoria.extend(protocolo.consultar_estado())
        tramas = protocolo.separar_tramas(memoria)
        self.assertEqual(tramas, [completa, protocolo.consultar_estado()])
        self.assertEqual(len(memoria), 0)


class PruebaTeclasYDescripciones(unittest.TestCase):
    def test_atajo_lleva_los_modificadores_delante(self):
        trama = protocolo.asignar_atajo(0, 0, [0xE0, 0x06])
        self.assertEqual(trama.hex(), "aabb737300 00e006".replace(" ", "") + "ccdd")

    def test_descripcion_translitera_el_espanol(self):
        self.assertEqual(protocolo.normalizar_descripcion("Revisión ñ"), "Revision n")

    def test_descripcion_se_recorta_a_veinte_bytes(self):
        larga = protocolo.normalizar_descripcion("a" * 40)
        self.assertEqual(len(larga), protocolo.MAXIMO_BYTES_DESCRIPCION)

    def test_rechaza_modo_o_tecla_fuera_de_rango(self):
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.asignar_atajo(3, 0, [0x04])
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.asignar_atajo(0, 9, [0x04])

    def test_macro_limitada_a_98_bytes(self):
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.asignar_macro(0, 0, [(1, 4)] * 60)

    def test_preparar_escritura_exige_alineacion(self):
        with self.assertRaises(protocolo.ErrorProtocolo):
            protocolo.preparar_escritura(4096, 1234)
        self.assertEqual(
            protocolo.preparar_escritura(4096, 8192).hex(),
            "aabb80" + "00" + "0010" + "00200000" + "ccdd",
        )


if __name__ == "__main__":
    unittest.main()
