"""Sabe cuándo ChatGPT está trabajando, sin que ChatGPT lo cuente.

Los agentes de línea de órdenes avisan de lo que hacen con enganches: llaman a
un programa nuestro al empezar una herramienta, al terminarla, al pedir permiso.
**ChatGPT no tiene nada de eso y no puede tenerlo.** Es una aplicación cerrada;
no hay archivo de configuración donde poner un enganche ni evento al que
apuntarse. Por eso el modo 2 se quedaba a oscuras mientras el modo 1 iba
encendiendo luces: no era un fallo, es que no llegaba ni un aviso.

Así que se mira, que es la única vía que queda. Windows publica una capa de
accesibilidad —la que usan los lectores de pantalla— y ChatGPT, por ser
Chromium por dentro, expone ahí sus botones con su nombre. Y hay uno que lo
dice todo: **«Detener» solo existe mientras está generando la respuesta.**
Cuando termina desaparece y vuelve el de enviar. Con eso salen las dos luces
que de verdad importan: está trabajando y ha terminado.

Lo que esto **no** puede hacer, para que conste y nadie lo prometa:

* No distingue *qué* está haciendo, solo que está en ello. Desde fuera,
  «pensando» y «ejecutando una herramienta» se ven exactamente igual.
* No ve cuándo ChatGPT te pide permiso. Ese aviso vive dentro de la
  conversación, no en un botón con nombre reconocible.
* Se apoya en cómo ChatGPT llama hoy a sus botones. Si un día los renombran,
  esto deja de acertar; por eso, cuando no reconoce ninguno, **se calla** en
  vez de inventarse un estado. Más vale una luz apagada que una que miente.

Solo mira cuando el teclado está en el modo cuyo dueño es ChatGPT. Fuera de ahí
no gasta ni una consulta: no tendría a quién encenderle la luz.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import threading
import time
from typing import Callable, Optional

from .registro import obtener

_log = obtener("chatgpt")

#: Cada cuánto se le echa un vistazo a la ventana.
INTERVALO_S = 1.2

#: Cuánto se espera antes de dar por terminada la respuesta. El botón de
#: «Detener» desaparece un instante entre bloques de texto, así que sin esta
#: espera el teclado cantaría «terminado» cada dos frases.
GRACIA_S = 2.5

#: Nombres del botón que solo existe mientras genera, en los idiomas en que se
#: ha visto. Se compara en minúsculas y por principio de cadena.
NOMBRES_DE_DETENER = ("detener", "stop", "parar", "interromper", "arrêter")

#: Botones que **también** empiezan por «detener» y no son el que buscamos.
#:
#: Al dictar, ChatGPT enseña «Detener dictado» —y Claude hace lo mismo—. Sin
#: esta lista, hablarle al micrófono encendía el azul de «está respondiendo»:
#: el vigía veía un botón de detener y daba por hecho que estaba generando.
#: Ocurría en el mismo segundo en que arrancaba el dictado, y desde fuera
#: parecía que ChatGPT contestaba solo.
NO_SON_DETENER = ("detener dictado", "stop dictation", "detener grabación")

#: Nombres del botón de enviar o de voz. Sirven para confirmar que estamos
#: leyendo la barra de escribir de verdad: si no aparece ninguno de los dos
#: grupos, la ventana no está donde creemos y más vale no afirmar nada.
NOMBRES_DE_ENVIAR = (
    "enviar",
    "send",
    "iniciar nuevo chat de voz",
    "start voice",
    "modo de voz",
    "voice mode",
    "dictar",
    "dictate",
)

_TIPO_BOTON = 50000

#: Área mínima para tomar una ventana por la aplicación. Las diminutas son
#: globos de aviso y menús flotantes, que también se llaman ChatGPT.
AREA_MINIMA = 200_000


def _empieza_por(nombre: str, prefijos: tuple[str, ...]) -> bool:
    n = nombre.strip().lower()
    return any(n.startswith(p) for p in prefijos)


def ventanas_de_chatgpt() -> list[int]:
    """Las ventanas visibles de ChatGPT, la más grande primero."""
    if os.name != "nt":
        return []
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    encontradas: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visitar(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        titulo = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, titulo, 512)
        if "chatgpt" not in titulo.value.lower():
            return True
        marco = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(marco)):
            return True
        area = (marco.right - marco.left) * (marco.bottom - marco.top)
        if area > AREA_MINIMA:
            encontradas.append((area, hwnd))
        return True

    user32.EnumWindows(visitar, None)
    encontradas.sort(reverse=True)
    return [hwnd for _, hwnd in encontradas]


class VigiaChatGPT:
    """Mira la ventana de ChatGPT y avisa cuando empieza y cuando termina.

    Vive en su propio hilo porque la capa de accesibilidad es COM y bloquea:
    consultarla desde el bucle de sucesos congelaría el teclado y el panel
    mientras la ventana tarda en contestar.
    """

    def __init__(
        self,
        avisar: Callable[[str], None],
        le_toca: Callable[[], bool],
    ) -> None:
        self._avisar = avisar
        self._le_toca = le_toca
        self._hilo: Optional[threading.Thread] = None
        self._parar = threading.Event()
        self.trabajando = False
        self.visible = False
        self.legible = False
        self._visto_generando = 0.0

    # --- ciclo de vida ----------------------------------------------------

    def arrancar(self) -> bool:
        if os.name != "nt":
            _log.debug("Solo se puede vigilar ChatGPT en Windows")
            return False
        try:
            import comtypes.client  # noqa: F401
        except ImportError:
            _log.info(
                "Sin comtypes no se puede leer el estado de ChatGPT; "
                "el modo de ChatGPT no encenderá luces"
            )
            return False
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, name="vigia-chatgpt", daemon=True)
        self._hilo.start()
        _log.info("Vigilando ChatGPT por la capa de accesibilidad")
        return True

    def detener(self) -> None:
        self._parar.set()

    def resumen(self) -> dict:
        return {
            "vigilando": bool(self._hilo and self._hilo.is_alive()),
            "ventana": self.visible,
            "legible": self.legible,
            "trabajando": self.trabajando,
        }

    # --- el bucle ---------------------------------------------------------

    def _bucle(self) -> None:
        import comtypes

        comtypes.CoInitialize()
        try:
            while not self._parar.is_set():
                try:
                    if self._le_toca():
                        self._mirar()
                    elif self.trabajando:
                        # Se cambió de modo con ChatGPT a medias: se olvida el
                        # estado, para no anunciar al volver algo de hace rato.
                        self.trabajando = False
                except Exception:  # noqa: BLE001 - la ventana puede irse a mitad
                    _log.debug("Fallo mirando ChatGPT", exc_info=True)
                self._parar.wait(INTERVALO_S)
        finally:
            comtypes.CoUninitialize()

    def _mirar(self) -> None:
        generando = self._leer_estado()
        self.legible = generando is not None
        if generando is None:
            return  # no se reconoce la ventana: mejor callarse
        ahora = time.monotonic()

        if generando:
            self._visto_generando = ahora
            if not self.trabajando:
                self.trabajando = True
                _log.info("ChatGPT empezó a responder")
                self._avisar("trabajando")
            return

        if self.trabajando and ahora - self._visto_generando >= GRACIA_S:
            self.trabajando = False
            _log.info("ChatGPT terminó de responder")
            self._avisar("terminado")

    def _leer_estado(self) -> Optional[bool]:
        """``True`` generando, ``False`` en reposo, ``None`` no se sabe."""
        ventanas = ventanas_de_chatgpt()
        self.visible = bool(ventanas)
        if not ventanas:
            return None

        from . import cuadro_de_texto as ct

        hwnd = ventanas[0]
        try:
            uia, UIA = ct._automatizacion()
            raiz = uia.ElementFromHandle(hwnd)
            marco = raiz.CurrentBoundingRectangle
            condicion = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, _TIPO_BOTON)
            hallados = raiz.FindAll(UIA.TreeScope_Descendants, condicion)
        except Exception:  # noqa: BLE001
            return None

        medio = (marco.top + marco.bottom) // 2
        detener = enviar = False
        for i in range(hallados.Length):
            try:
                elemento = hallados.GetElement(i)
                if elemento.CurrentBoundingRectangle.top <= medio:
                    continue  # la barra de escribir vive en la mitad de abajo
                nombre = elemento.CurrentName or ""
            except Exception:  # noqa: BLE001
                continue
            if _empieza_por(nombre, NO_SON_DETENER):
                continue   # es el del dictado, no el de generar
            if _empieza_por(nombre, NOMBRES_DE_DETENER):
                detener = True
            elif _empieza_por(nombre, NOMBRES_DE_ENVIAR):
                enviar = True

        if detener:
            return True
        if enviar:
            return False
        # Ni uno ni otro: o la ventana está tapada, o ChatGPT cambió los
        # nombres de sus botones. En ninguno de los dos casos conviene afirmar.
        return None


__all__ = ["VigiaChatGPT", "ventanas_de_chatgpt", "INTERVALO_S", "GRACIA_S"]
