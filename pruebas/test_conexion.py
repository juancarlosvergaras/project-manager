"""Que el teclado no se pierda para siempre por apagarlo una vez.

Estas pruebas cubren un fallo que costó una tarde entera y que se manifestaba
de tres formas que parecían no tener nada que ver: la web decía «todavía no hay
teclado» con el teclado encendido delante, la barra de luz se quedaba
congelada, y al pulsar el micrófono en el modo 1 el dictado se iba a la ventana
de ChatGPT. Las tres salían de lo mismo, así que se prueba lo mismo.
"""

from __future__ import annotations

import asyncio
import unittest

from pruebas.base import PruebaAislada

from tecladoia.config import Ajustes
from tecladoia.dispositivo import GestorTeclado
from tecladoia.transporte.base import ErrorTransporte, Transporte


class TransporteDeMentira(Transporte):
    """Un transporte que se puede apagar, colgar y romper a voluntad."""

    nombre_legible = "de mentira"

    def __init__(self) -> None:
        self.canal = False
        self.vivo = False
        self.cuelga_al_conectar = False
        #: Como el de verdad cuando Windows se atasca: ni cancelándolo termina.
        self.ignora_la_cancelacion = False
        self.escrituras = 0
        self.intentos_de_conectar = 0

    @property
    def conectado(self) -> bool:
        # Como el de verdad: solo consta vivo si hemos hablado con él.
        return self.canal and self.vivo

    @property
    def canal_abierto(self) -> bool:
        return self.canal

    async def conectar(self) -> None:
        self.intentos_de_conectar += 1
        if self.cuelga_al_conectar:
            try:
                await asyncio.sleep(3600)  # se queda esperando, como WinRT
            except asyncio.CancelledError:
                if not self.ignora_la_cancelacion:
                    raise
                # Colgada de verdad: ni cancelándola se muere. Es lo que hace
                # la pila Bluetooth de Windows y lo que dejaba inútil el plazo.
                await asyncio.sleep(3600)
        self.canal = True
        self.vivo = True

    async def desconectar(self) -> None:
        self.canal = False
        self.vivo = False

    async def enviar_comando(self, trama: bytes) -> None:
        self.escrituras += 1
        if not self.vivo:
            self.canal = False  # como el de verdad: la escritura falla y suelta
            raise ErrorTransporte("el teclado no contesta")

    async def enviar_datos(self, bloque: bytes) -> None:
        await self.enviar_comando(bloque)

    async def descripcion(self) -> str:
        return self.nombre_legible

    def escuchar(self, callback) -> None:
        self._oyente = callback


def _gestor(transporte: Transporte) -> GestorTeclado:
    ajustes = Ajustes()
    # El transporte de mentira no manda notificaciones, así que cada consulta
    # agota su plazo. Con el de verdad (1,2 s) estas pruebas tardarían más en
    # esperar que en probar.
    ajustes.espera_palanca_s = 0.05
    return GestorTeclado(ajustes, transporte)


class PruebaCirculoVicioso(PruebaAislada):
    def test_el_latido_intenta_aunque_no_conste_conectado(self):
        """El sondeo no puede pedirle permiso a «conectado».

        Es el fallo de raíz. Un teclado dormido deja de constar conectado; si el
        sondeo se saltara por eso, nadie volvería a escribirle, y como solo una
        escritura acertada demuestra que sigue ahí, no volvería a constar
        conectado nunca. Se quedaba muerto hasta reiniciar el servicio.
        """
        t = TransporteDeMentira()
        t.canal, t.vivo = True, False   # canal abierto, pero no consta vivo
        g = _gestor(t)
        self.assertFalse(g.conectado)
        self.assertTrue(g.puede_intentarse)

        async def caso():
            await g.consultar_estado(espera_s=0.05)

        asyncio.run(caso())
        self.assertGreater(t.escrituras, 0, "el latido ni lo intentó")

    def test_sin_canal_no_se_intenta(self):
        """Lo contrario también: sin canal no hay nada que probar."""
        t = TransporteDeMentira()
        g = _gestor(t)
        self.assertFalse(g.puede_intentarse)

        async def caso():
            self.assertIsNone(await g.consultar_estado(espera_s=0.05))

        asyncio.run(caso())
        self.assertEqual(t.escrituras, 0)

    def test_una_escritura_fallida_suelta_el_canal(self):
        """Así es como se entera de que se fue: intentándolo."""
        t = TransporteDeMentira()
        t.canal, t.vivo = True, False
        g = _gestor(t)

        async def caso():
            await g.consultar_estado(espera_s=0.05)

        asyncio.run(caso())
        self.assertFalse(t.canal_abierto, "debería haber soltado el canal")


class PruebaReconexion(PruebaAislada):
    def test_una_conexion_colgada_no_atasca_el_bucle(self):
        """El fallo que dejó el servicio mudo una tarde entera.

        Ningún paso de la pila Bluetooth de Windows trae plazo propio, y con el
        teclado apagado se quedan esperando indefinidamente. Al apagar el
        teclado se soltaba el canal —correcto— y el intento de reabrirlo se
        colgaba dentro de WinRT: el bucle no daba otra vuelta nunca más.
        """
        t = TransporteDeMentira()
        t.cuelga_al_conectar = True

        async def caso():
            g = _gestor(t)
            tarea = asyncio.create_task(g.mantener_conexion(intervalo_s=0.01))
            import tecladoia.dispositivo as d

            previo = d.PLAZO_DE_RECONEXION_S
            d.PLAZO_DE_RECONEXION_S = 0.05  # plazo de juguete para la prueba
            try:
                await asyncio.sleep(0.6)
            finally:
                d.PLAZO_DE_RECONEXION_S = previo
                tarea.cancel()
                try:
                    await tarea
                except asyncio.CancelledError:
                    pass
            return t.intentos_de_conectar

        intentos = asyncio.run(caso())
        self.assertGreater(
            intentos, 1, "se quedó colgado en el primer intento y no reintentó"
        )

    def test_una_conexion_que_ni_cancelandola_muere_tampoco_atasca(self):
        """El segundo intento de arreglarlo, que tampoco bastaba.

        ``asyncio.wait_for`` cancela al vencer el plazo, pero después **espera
        a que la cancelación termine**. Con una llamada de Windows colgada de
        verdad eso no llega nunca, así que el plazo se colgaba igual que lo que
        debía proteger: un aviso de «no contesta» y catorce horas de silencio.

        Ahora el intento se abandona en vez de esperarlo.
        """
        t = TransporteDeMentira()
        t.cuelga_al_conectar = True
        t.ignora_la_cancelacion = True

        async def caso():
            g = _gestor(t)
            import tecladoia.dispositivo as d

            previo = d.PLAZO_DE_RECONEXION_S
            d.PLAZO_DE_RECONEXION_S = 0.05
            tarea = asyncio.create_task(g.mantener_conexion(intervalo_s=0.01))
            try:
                await asyncio.sleep(0.5)
                vueltas_dadas = t.intentos_de_conectar
            finally:
                d.PLAZO_DE_RECONEXION_S = previo
                tarea.cancel()
                try:
                    await tarea
                except asyncio.CancelledError:
                    pass
            return tarea, vueltas_dadas

        tarea, _ = asyncio.run(caso())
        self.assertTrue(tarea.done(), "el bucle se quedó colgado")

    def test_un_intento_que_no_muere_no_bloquea_para_siempre(self):
        """Y si la llamada colgada no se muere nunca, se empieza sin ella.

        Esperar indefinidamente a que muera sería cambiar un atasco por otro:
        una sola llamada atascada dentro de Windows dejaría el teclado
        inalcanzable para siempre.
        """
        t = TransporteDeMentira()
        t.cuelga_al_conectar = True
        t.ignora_la_cancelacion = True

        async def caso():
            g = _gestor(t)
            import tecladoia.dispositivo as d

            plazo, espera = d.PLAZO_DE_RECONEXION_S, d.ESPERA_ANTES_DE_INSISTIR_S
            d.PLAZO_DE_RECONEXION_S = 0.05
            d.ESPERA_ANTES_DE_INSISTIR_S = 0.1
            tarea = asyncio.create_task(g.mantener_conexion(intervalo_s=0.01))
            try:
                await asyncio.sleep(0.3)
                colgados = t.intentos_de_conectar
                t.cuelga_al_conectar = False   # el teclado vuelve a aparecer
                await asyncio.sleep(0.4)
                recuperado = g.conectado
            finally:
                d.PLAZO_DE_RECONEXION_S, d.ESPERA_ANTES_DE_INSISTIR_S = plazo, espera
                tarea.cancel()
                try:
                    await tarea
                except asyncio.CancelledError:
                    pass
            return colgados, recuperado

        colgados, recuperado = asyncio.run(caso())
        self.assertGreater(colgados, 1, "no insistió pese al plazo de abandono")
        self.assertTrue(recuperado, "no se recuperó tras dejar de colgarse")

    def test_el_teclado_vuelve_solo_cuando_se_enciende(self):
        """Encenderlo otra vez tiene que bastar. Sin reiniciar nada."""

        async def caso():
            t = TransporteDeMentira()
            g = _gestor(t)
            tarea = asyncio.create_task(g.mantener_conexion(intervalo_s=0.02))
            await asyncio.sleep(0.15)
            self.assertTrue(g.conectado, "no lo abrió al arrancar")

            t.vivo = False          # se apaga el teclado
            await g.consultar_estado(espera_s=0.05)   # el latido se entera
            self.assertFalse(g.puede_intentarse, "no soltó el canal")

            t.vivo = True           # se vuelve a encender
            await asyncio.sleep(0.4)
            recuperado = g.conectado
            tarea.cancel()
            try:
                await tarea
            except asyncio.CancelledError:
                pass
            return recuperado

        self.assertTrue(asyncio.run(caso()), "no se recuperó al encenderlo")


if __name__ == "__main__":
    unittest.main()
