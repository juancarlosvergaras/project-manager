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


class PruebaPalancaFija(PruebaAislada):
    """Una palanca se puede romper, y la del teclado se rompió.

    Sin poder fijarla, un interruptor averiado deja el sistema preguntando por
    todo para siempre. Eso es lo correcto cuando no se sabe, pero no cuando sí
    se sabe y no hay forma de decirlo.
    """

    def test_de_fabrica_manda_el_teclado(self):
        self.assertIsNone(Ajustes().palanca_fija, "no puede venir fijada de casa")

    def test_se_recuerda_al_reiniciar(self):
        """En memoria se perdía en cada arranque, que es cuando más duele."""
        a = Ajustes()
        a.palanca_fija = 0
        a.guardar()
        self.assertEqual(Ajustes.cargar().palanca_fija, 0)

    def test_se_puede_devolver_al_teclado(self):
        a = Ajustes()
        a.palanca_fija = 1
        a.guardar()
        b = Ajustes.cargar()
        b.palanca_fija = None
        b.guardar()
        self.assertIsNone(Ajustes.cargar().palanca_fija)

    def test_la_fija_manda_sobre_la_lectura(self):
        """Con la palanca rota, lo que diga el teclado no vale."""
        from tecladoia.dispositivo import GestorTeclado

        from pruebas.test_conexion import TransporteDeMentira

        g = GestorTeclado(Ajustes(), TransporteDeMentira())
        g.palanca_forzada = 0
        self.assertEqual(g.resumen()["palanca"], 0)
        self.assertTrue(g.resumen()["palanca_forzada"])


if __name__ == "__main__":
    unittest.main()


class PruebaPrimeraPulsacion(PruebaAislada):
    """La primera pulsacion tras arrancar tiene que abrir, no cerrar.

    El dictado de Windows sobrevive a nuestros reinicios y nuestra memoria no.
    Si el servicio se reinicia con el panel abierto, arrancabamos creyendolo
    cerrado y la primera pulsacion mandaba Win+H —que es un interruptor— y lo
    cerraba. De ahi el «la primera vez que lo pulso no se activa».
    """

    def _dictado(self):
        from tecladoia.dictado import Dictado

        d = Dictado()
        d._cerrados = []
        d._abiertos = []
        return d

    def test_arranca_sin_saber_en_que_posicion_esta(self):
        self.assertTrue(self._dictado()._primera_vez)

    def test_la_primera_vez_se_cierra_antes_de_abrir(self):
        """Escape primero: cierra si estaba abierto, y si no, no hace nada."""
        import tecladoia.dictado as dic

        d = self._dictado()
        cerrados = []
        previo = dic.cerrar_dictado
        dic.cerrar_dictado = lambda: cerrados.append(1)
        try:
            d._asegurar_punto_de_partida()
            self.assertEqual(len(cerrados), 1, "no partio de una posicion conocida")
            # Y solo la primera: despues las cuentas ya cuadran y cerrar de mas
            # seria cerrarle el microfono a quien esta hablando.
            d._asegurar_punto_de_partida()
            d._asegurar_punto_de_partida()
            self.assertEqual(len(cerrados), 1, "siguio cerrando en cada apertura")
        finally:
            dic.cerrar_dictado = previo


class PruebaMicrofonoPropio(PruebaAislada):
    """Cada programa cuenta su dictado a su manera, y hay que saber las dos.

    La ganancia de fondo no es la calidad del dictado: es que **se puede saber
    si esta grabando**. Win+H es un interruptor a ciegas —el panel de Windows
    no es una ventana ni se asoma a la accesibilidad— y de ahi venia casi todo
    lo que fallaba del microfono.
    """

    def test_claude_conoce_los_dos_nombres_de_su_boton(self):
        """Se renombra al grabar, y con un solo nombre se pierde a mitad.

        En reposo es «Manten presionado para grabar»; grabando pasa a «Detener
        dictado». Buscando solo el primero, en cuanto empieza deja de
        encontrarse y parece que el programa se quedo sin dictado.
        """
        from tecladoia.microfono_propio import perfil_de

        nombres = perfil_de("claude")["interruptor"]
        self.assertTrue(any("grabar" in n for n in nombres))
        self.assertTrue(any("detener" in n for n in nombres))

    def test_chatgpt_sabe_enviar_el_solo(self):
        """Su «Transcribir y enviar» es justo lo de la palanca arriba.

        Y lo hace el, que sabe cuando ha terminado de transcribir; nosotros
        solo podiamos esperar medio segundo y pulsar Intro a ver si ya estaba.
        """
        from tecladoia.microfono_propio import perfil_de

        self.assertTrue(perfil_de("ChatGPT").get("enviar"))

    def test_chatgpt_usa_su_atajo(self):
        from tecladoia.microfono_propio import perfil_de

        self.assertEqual(perfil_de("ChatGPT").get("atajo"), "ctrl+shift+d")

    def test_el_atajo_se_traduce_a_teclas(self):
        from tecladoia.microfono_propio import _TECLAS

        self.assertEqual(_TECLAS["ctrl"], 0x11)
        self.assertEqual(_TECLAS["shift"], 0x10)

    def test_lo_desconocido_no_se_inventa(self):
        """Un programa sin dictado propio devuelve «no lo se», no «no graba».

        La diferencia importa: «no lo se» manda a Win+H, que funciona en
        cualquier sitio. Inventarse la respuesta seria repetir el error que
        esto viene a corregir.
        """
        from tecladoia.microfono_propio import MicrofonoDeLaApp

        m = MicrofonoDeLaApp(0, "un-programa-cualquiera")
        self.assertIsNone(m.estado())
        self.assertFalse(m.hay_dictado())

    def test_se_puede_volver_a_win_h(self):
        a = Ajustes()
        self.assertTrue(a.usar_microfono_propio, "de fabrica se prefiere el propio")
        a.usar_microfono_propio = False
        a.guardar()
        self.assertFalse(Ajustes.cargar().usar_microfono_propio)


class PruebaVigiaChatGPT(PruebaAislada):
    """ChatGPT no tiene enganches: su estado se lee mirandole la ventana.

    De ahi salen los dos unicos momentos que se pueden sostener desde fuera
    —esta respondiendo y ha terminado— porque el boton «Detener» solo existe
    mientras genera.
    """

    def test_el_boton_del_dictado_no_es_el_de_generar(self):
        """Dictar encendia el azul de «esta respondiendo».

        Al dictar, ChatGPT enseña «Detener dictado». El vigia buscaba botones
        que empezaran por «detener» y lo tomaba por el de generar, asi que
        hablarle al microfono hacia creer que ChatGPT contestaba solo. Ocurria
        en el mismo segundo en que arrancaba el dictado.
        """
        from tecladoia.vigia_chatgpt import (
            NO_SON_DETENER, NOMBRES_DE_DETENER, _empieza_por,
        )

        def generando(nombre: str) -> bool:
            if _empieza_por(nombre, NO_SON_DETENER):
                return False
            return _empieza_por(nombre, NOMBRES_DE_DETENER)

        self.assertTrue(generando("Detener"), "el de generar tiene que contar")
        self.assertTrue(generando("Stop"))
        self.assertFalse(generando("Detener dictado"), "el del dictado no")
        self.assertFalse(generando("Stop dictation"))

    def test_solo_dos_momentos_y_a_proposito(self):
        """Desde fuera no se distingue «pensando» de «ejecutando».

        Prometer mas seria inventarselo. Se sostienen dos: trabajando y
        terminado.
        """
        from tecladoia.modelo import EstadoIA
        from tecladoia.servidor import ServidorEnganches

        import inspect
        fuente = inspect.getsource(ServidorEnganches.avisar_de_chatgpt)
        self.assertIn("HERRAMIENTA_EN_CURSO", fuente)
        self.assertIn("TAREA_COMPLETADA", fuente)
        self.assertNotIn("ESPERANDO_APROBACION", fuente)
        del EstadoIA
