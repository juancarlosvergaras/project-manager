"""El protocolo de la Botonera arma exactamente los bytes que el teclado obedeció el 6/9/2026.

Las tiras de bytes de referencia son las que se le mandaron al aparato y se
comprobaron escuchando sus pulsaciones (teclas y perillas) o mirándolo (luces).
"""

from __future__ import annotations

import unittest

from pruebas.base import RAIZ  # noqa: F401  (fija sys.path)
from botonera import protocolo
from botonera.protocolo import Accion, ErrorProtocolo, Luces


def sin_ceros(b: bytes) -> str:
    return b.rstrip(b"\x00").hex(" ")


class PruebaPiezas(unittest.TestCase):
    def test_ids_como_se_midieron(self):
        self.assertEqual([protocolo.id_de_pieza(i) for i in range(12)], list(range(1, 13)))
        # perillas: 16-18, 19-21, 22-24 (giro, pulsación, giro)
        self.assertEqual([protocolo.id_de_pieza(i) for i in range(12, 21)], list(range(16, 25)))
        self.assertEqual(protocolo.pieza_de_perilla(1, 1), 16)
        self.assertEqual(protocolo.id_de_pieza(protocolo.pieza_de_perilla(2, 2)), 24)
        self.assertEqual(len(protocolo.NOMBRES_DE_LAS_PIEZAS), 21)
        with self.assertRaises(ErrorProtocolo):
            protocolo.id_de_pieza(21)


class PruebaMensajes(unittest.TestCase):
    def test_todos_miden_65(self):
        for m in protocolo.mensajes_de_pieza(0, 0, Accion.desde_texto("f13")) + [protocolo.mensaje_de_luces(0, Luces(1, "#ff0000"))]:
            self.assertEqual(len(m), 65)

    def test_tecla_simple_como_se_grabo(self):
        orden, fin = protocolo.mensajes_de_pieza(0, 0, Accion.desde_texto("f13"))
        self.assertEqual(sin_ceros(orden), "03 fd 01 01 01 00 01 00 00 68")
        self.assertEqual(sin_ceros(fin), "03 fd fe ff")

    def test_mayus_f13_en_la_primera_perilla(self):
        orden, _ = protocolo.mensajes_de_pieza(0, 12, Accion.desde_texto("mayus-f13"))
        self.assertEqual(sin_ceros(orden), "03 fd 10 01 01 00 02 00 00 f2 00 00 68")

    def test_perfil_va_desde_1_en_teclas_y_desde_0_en_luces(self):
        orden, _ = protocolo.mensajes_de_pieza(2, 5, Accion.desde_texto("ctrl-c"))
        self.assertEqual(orden[2:4].hex(" "), "06 03")
        luces = protocolo.mensaje_de_luces(2, Luces(1, "#0000ff"))
        self.assertEqual(luces[:8].hex(" "), "03 fe b0 02 01 00 00 ff")

    def test_luces_rojas_como_se_vieron(self):
        m = protocolo.mensaje_de_luces(0, Luces(1, "#ff0000"))
        self.assertEqual(m[:8].hex(" "), "03 fe b0 00 01 ff 00 00")
        self.assertEqual(m[8:56], bytes([0xFF, 0, 0]) * 16)
        self.assertEqual(m[56:], bytes(9))

    def test_secuencia_multimedia_y_raton(self):
        orden, _ = protocolo.mensajes_de_pieza(0, 1, Accion.desde_texto("ctrl-c, ctrl-v"))
        self.assertEqual(sin_ceros(orden), "03 fd 02 01 01 00 04 00 00 f1 00 00 06 00 00 f1 00 00 19")
        orden, _ = protocolo.mensajes_de_pieza(0, 13, Accion.desde_texto("vol+"))
        self.assertEqual(sin_ceros(orden), "03 fd 11 01 02 00 02 00 00 e9")
        orden, _ = protocolo.mensajes_de_pieza(0, 13, Accion.desde_texto("calculadora"))
        self.assertEqual(sin_ceros(orden), "03 fd 11 01 02 00 02 00 00 92 00 00 01")
        orden, _ = protocolo.mensajes_de_pieza(0, 14, Accion.desde_texto("rueda-abajo"))
        self.assertEqual(orden[:5].hex(" "), "03 fd 12 01 03")
        self.assertEqual(orden[5:22].hex(" "), "01 04 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ff")
        orden, _ = protocolo.mensajes_de_pieza(0, 14, Accion.desde_texto("ctrl-rueda-arriba"))
        self.assertEqual(orden[9], 0xF1)
        self.assertEqual(orden[21], 0x01)
        orden, _ = protocolo.mensajes_de_pieza(0, 14, Accion.desde_texto("clic-central"))
        self.assertEqual(orden[12], 0x04)

    def test_nada_deja_la_pieza_muda(self):
        orden, _ = protocolo.mensajes_de_pieza(1, 0, Accion.desde_texto("nada"))
        self.assertEqual(sin_ceros(orden), "03 fd 01 02 01")

    def test_perfil_entero(self):
        acciones = [Accion.desde_texto("a")] * 21
        mensajes = protocolo.mensajes_de_perfil(1, acciones, Luces(2, "#123456"))
        self.assertEqual(len(mensajes), 21 * 2 + 1)
        self.assertEqual(mensajes[-1][:5].hex(" "), "03 fe b0 01 02")
        with self.assertRaises(ErrorProtocolo):
            protocolo.mensajes_de_perfil(0, acciones[:-1])


class PruebaAcciones(unittest.TestCase):
    def test_texto_y_vuelta(self):
        for texto, esperado in [
            ("Ctrl-Mayús-Esc".lower().replace("ú", "u"), "ctrl-mayus-esc"), ("shift-a", "mayus-a"), ("enter", "intro"),
            ("ctrl-c,  ctrl-v", "ctrl-c, ctrl-v"), ("win", "win"), ("VOL+", "vol+"), ("wheel-up", "rueda-arriba"),
            ("", "nada"), ("nada", "nada"), ("ctrl-mayus-alt-f13", "ctrl-mayus-alt-f13"),
        ]:
            self.assertEqual(str(Accion.desde_texto(texto)), esperado, texto)

    def test_familias(self):
        self.assertEqual(Accion.desde_texto("clic").familia, "raton")
        self.assertEqual(Accion.desde_texto("silencio").familia, "multimedia")
        self.assertEqual(Accion.desde_texto("ctrl-a").familia, "teclado")
        self.assertEqual(Accion.desde_texto("ctrl-a").tipo, 1)
        self.assertEqual(Accion.desde_texto("silencio").tipo, 2)
        self.assertEqual(Accion.desde_texto("clic").tipo, 3)

    def test_lo_que_no_vale(self):
        for malo in ("ctrl-loquesea", "a-b", "ctrl-ctrl-a", "ctrl-a,,b", ", ".join(["ctrl-a"] * 10)):
            with self.assertRaises(ErrorProtocolo, msg=malo):
                Accion.desde_texto(malo)

    def test_codigo_crudo(self):
        a = Accion.desde_texto("<0x65>")
        self.assertEqual(a.a_carga()[-1], 0x65)


class PruebaLuces(unittest.TestCase):
    def test_valida_y_normaliza(self):
        self.assertEqual(Luces(1, "#FF8800").color, "#ff8800")
        self.assertEqual(Luces(4, "#000000").nombre_del_modo, "arcoíris por filas")
        with self.assertRaises(ErrorProtocolo):
            Luces(1, "rojo")
        with self.assertRaises(ErrorProtocolo):
            Luces(300, "#000000")


if __name__ == "__main__":
    unittest.main()
