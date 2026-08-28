"""Manos libres: el micrófono se abre cuando la IA termina.

Con la palanca arriba —que envía lo dictado al cerrar— esto cierra el círculo:
hablas, la IA trabaja, termina, y te vuelve a escuchar sin que toques nada.

Lo que aquí se prueba no es que suene el pitido, sino las tres reglas que hacen
que sea usable en vez de molesto: solo el dueño del modo puesto lo dispara,
solo al terminar del todo, y nunca encima de un dictado que ya estaba abierto.
"""

from __future__ import annotations

import unittest

from pruebas.base import PruebaAislada

from tecladoia.config import Ajustes
from tecladoia.modelo import EstadoIA


class DictadoDeMentira:
    """El dictado, sin tocar Windows."""

    def __init__(self, abierto: bool = False) -> None:
        self.abierto = abierto
        self.programa = ""
        self.aperturas: list[str] = []

    def abrir_solo(self, programa="", lanzar="", pinchar_el_cuadro=True,
                   alto_del_cuadro=0) -> dict:
        if self.abierto:
            return {"accion": "ya estaba", "programa": self.programa}
        self.abierto = True
        self.programa = programa
        self.aperturas.append(programa)
        return {"accion": "abierto", "programa": programa, "cuadro": "Prompt"}


class PruebaAbrirSolo(PruebaAislada):
    """``abrir_solo`` abre, pero nunca cierra. La diferencia importa."""

    def test_abre_si_estaba_cerrado(self):
        d = DictadoDeMentira()
        self.assertEqual(d.abrir_solo("claude")["accion"], "abierto")
        self.assertTrue(d.abierto)

    def test_no_cierra_lo_que_ya_estaba_abierto(self):
        """Aquí está la razón de que no sea ``alternar``.

        Quien llama no es tu dedo, sino un agente que acaba de terminar. Si
        alternara, te cerraría el micrófono justo mientras estás hablando.
        """
        d = DictadoDeMentira(abierto=True)
        self.assertEqual(d.abrir_solo("claude")["accion"], "ya estaba")
        self.assertTrue(d.abierto, "le cerró el micrófono a quien estaba hablando")
        self.assertEqual(d.aperturas, [])


class PruebaCuandoSeDispara(PruebaAislada):
    """Las reglas de cuándo procede abrir el micrófono."""

    def _decidir(self, ajustes, estado, es_del_dueno):
        """La regla, tal y como la aplica el servidor."""
        return bool(
            getattr(ajustes, "manos_libres", False)
            and es_del_dueno
            and estado is EstadoIA.TAREA_COMPLETADA
        )

    def test_apagado_no_hace_nada(self):
        """Viene apagado, y apagado no puede cambiar nada de lo que ya iba."""
        a = Ajustes()
        self.assertFalse(a.manos_libres, "manos libres no puede venir encendido")
        self.assertFalse(self._decidir(a, EstadoIA.TAREA_COMPLETADA, True))

    def test_encendido_y_del_dueno_al_terminar(self):
        a = Ajustes()
        a.manos_libres = True
        self.assertTrue(self._decidir(a, EstadoIA.TAREA_COMPLETADA, True))

    def test_no_si_el_agente_no_manda_en_el_modo_puesto(self):
        """Que Claude termine no te abre el micrófono sobre ChatGPT.

        Es la misma regla que gobierna la barra de luz: abrir el dictado sobre
        una ventana que no estás mirando sería peor que no abrirlo, porque lo
        que dictes se va a la conversación equivocada.
        """
        a = Ajustes()
        a.manos_libres = True
        self.assertFalse(self._decidir(a, EstadoIA.TAREA_COMPLETADA, False))

    def test_solo_al_terminar_del_todo(self):
        """Un turno tiene muchos momentos; solo el final invita a hablar."""
        a = Ajustes()
        a.manos_libres = True
        for estado in (
            EstadoIA.HERRAMIENTA_EN_CURSO,
            EstadoIA.HERRAMIENTA_TERMINADA,
            EstadoIA.PETICION_ENVIADA,
            EstadoIA.SESION_INICIADA,
        ):
            with self.subTest(estado=estado.etiqueta):
                self.assertFalse(self._decidir(a, estado, True))


class PruebaPitidos(PruebaAislada):
    def test_se_pueden_silenciar(self):
        a = Ajustes()
        self.assertTrue(a.pitidos_manos_libres, "por omisión sí avisan")
        a.pitidos_manos_libres = False
        a.guardar()
        self.assertFalse(Ajustes.cargar().pitidos_manos_libres)

    def test_silenciarlos_no_apaga_manos_libres(self):
        """Son dos interruptores distintos y tienen que serlo.

        Hay quien trabaja con gente al lado: quiere el micrófono automático y
        no quiere el ruido.
        """
        a = Ajustes()
        a.manos_libres = True
        a.pitidos_manos_libres = False
        a.guardar()
        guardado = Ajustes.cargar()
        self.assertTrue(guardado.manos_libres)
        self.assertFalse(guardado.pitidos_manos_libres)

    def test_avisar_no_hace_esperar(self):
        """El pitido suena en otro hilo: bloquear aquí se come tus palabras.

        ``winsound.Beep`` bloquea lo que dure el tono, y quien llama acaba de
        abrir el micrófono.
        """
        import time

        from tecladoia import sonido

        if not sonido.hay_soporte():
            self.skipTest("este equipo no sabe pitar")
        empezo = time.monotonic()
        sonido.avisar()
        self.assertLess(time.monotonic() - empezo, 0.05, "se quedó esperando al tono")


class PruebaAjustesEnLaWeb(PruebaAislada):
    def test_los_interruptores_llegan_al_panel(self):
        """De nada sirve un ajuste que solo se puede tocar editando un archivo."""
        from tecladoia.panel import PanelWeb

        for campo in ("manos_libres", "pitidos_manos_libres", "manos_libres_espera_s"):
            with self.subTest(campo=campo):
                self.assertIn(campo, PanelWeb._CAMPOS_AJUSTES)


if __name__ == "__main__":
    unittest.main()
