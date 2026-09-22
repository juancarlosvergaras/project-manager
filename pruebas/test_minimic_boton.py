"""El botón Bluetooth de una tecla (AI_VOICE): lo puro, sin aparato."""

from __future__ import annotations

import unittest

from pruebas.base import RAIZ  # noqa: F401  (fija sys.path)
from minimic import boton


class PruebaRutas(unittest.TestCase):
    RAW = r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}_LOCALMFG&0002&Col01#8&649811&0&0000#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"
    HIDAPI = r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}_LOCALMFG&0002&Col01#8&649811&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}\KBD"
    OTRA = r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}_LOCALMFG&0002&Col02#8&649811&0&0001#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"

    def test_instancia_pnp_desde_la_ruta(self):
        self.assertEqual(
            boton.instancia_de(self.HIDAPI),
            r"HID\{00001124-0000-1000-8000-00805f9b34fb}_LOCALMFG&0002&Col01\8&649811&0&0000",
        )

    def test_raw_input_y_hidapi_nombran_la_misma_interfaz(self):
        self.assertTrue(boton.misma_interfaz(self.RAW, self.HIDAPI))
        self.assertFalse(boton.misma_interfaz(self.RAW, self.OTRA), "otra colección del mismo aparato no es la del teclado")

    def test_direccion_del_padre(self):
        padre = r"BTHENUM\{00001124-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002\7&1B9BF59C&0&5BCBA23EA614_C00000000"
        self.assertEqual(boton.direccion_del_padre(padre), "5BCBA23EA614")
        self.assertEqual(boton.direccion_del_padre(r"USB\VID_514C&PID_8850\7&1"), "")


class PruebaRebote(unittest.TestCase):
    def test_altgr_llega_como_dos_teclas_y_cuenta_una(self):
        r = boton.Rebote(0.7)
        self.assertTrue(r.es_nueva(10.0))     # Ctrl (falso) del AltGr
        self.assertFalse(r.es_nueva(10.01))   # Alt derecho, 10 ms después
        self.assertFalse(r.es_nueva(10.5))
        self.assertTrue(r.es_nueva(10.8))     # la pulsación siguiente


class PruebaEscucha(unittest.TestCase):
    def test_apuntar_a_decide_de_quien_es_la_pulsacion(self):
        e = boton.EscuchaBoton(lambda: None)
        self.assertFalse(e.es_del_boton(PruebaRutas.RAW), "sin botón a la vista no es de nadie")
        e.apuntar_a([PruebaRutas.HIDAPI])
        self.assertTrue(e.es_del_boton(PruebaRutas.RAW))
        self.assertFalse(e.es_del_boton(r"\\?\ACPI#HPQ8002#4&284fd6de&0#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}"))
        e.apuntar_a([])
        self.assertFalse(e.es_del_boton(PruebaRutas.RAW))


class PruebaPulsacionLarga(unittest.TestCase):
    def test_mantener_apretado_cuenta_una_vez(self):
        """Windows repite la tecla mientras el botón sigue apretado; pasado el
        rebote eso abría el dictado otra vez (21/9/2026)."""
        e = boton.EscuchaBoton(lambda: None)
        CTRL, ALT = 0x11, 0x12
        self.assertTrue(e.pulsacion_nueva(CTRL, False, 10.0))    # AltGr: Ctrl…
        self.assertFalse(e.pulsacion_nueva(ALT, False, 10.01))   # …y Alt derecho: la misma pulsación
        for t in (10.05, 10.5, 11.0, 11.5, 12.0):                 # repetición automática
            self.assertFalse(e.pulsacion_nueva(ALT, False, t))
            self.assertFalse(e.pulsacion_nueva(CTRL, False, t))
        self.assertFalse(e.pulsacion_nueva(ALT, True, 12.1))     # soltar no cuenta
        self.assertFalse(e.pulsacion_nueva(CTRL, True, 12.1))
        self.assertTrue(e.pulsacion_nueva(CTRL, False, 13.0))    # la pulsación siguiente sí


class PruebaServicioConBoton(unittest.TestCase):
    def test_resumen_cuenta_el_boton(self):
        import os

        from minimic.config import Ajustes
        from minimic.servicio import Servicio
        from minimic import dispositivo

        os.environ.setdefault("MINIMIC_INICIO", os.path.join(os.environ.get("TEMP", "."), "minimic-prueba-boton"))
        s = Servicio(Ajustes(boton_bluetooth="AI_VOICE"), dispositivo.Teclado(lambda: None))
        r = s.resumen()["boton"]
        self.assertEqual(r["nombre"], "AI_VOICE")
        self.assertTrue(r["buscado"])
        self.assertFalse(r["conectado"])
        s.estado.boton = boton.Boton("AI_VOICE", "5BCBA23EA614", "{X}", ["ruta"])
        s.estado.boton_microfono = "AI_VOICE Hands-Free"
        r = s.resumen()["boton"]
        self.assertTrue(r["conectado"])
        self.assertEqual(r["direccion"], "5BCBA23EA614")
        self.assertEqual(r["microfono"]["nombre"], "AI_VOICE Hands-Free")
