"""Usar el micrófono de la propia aplicación en vez del dictado de Windows.

Claude y ChatGPT traen su dictado dentro, y es mejor que el de Windows por una
razón que no es de calidad sino de mecánica: **se puede saber si está
grabando**.

Win+H es un interruptor a ciegas. El panel de dictado de Windows no es una
ventana ni se asoma a la capa de accesibilidad —se buscó y no está—, así que no
hay forma de saber en qué posición está. De ahí venían todos los males del
micrófono: pulsabas para cerrar y se abría, Windows lo cerraba solo tras un
silencio y nuestras cuentas se desalineaban, y la primera pulsación tras
reiniciar hacía lo contrario de lo que querías.

**Cada programa lo cuenta a su manera**, y hay que hablar los dos idiomas:

* **Claude** tiene un solo botón que se enciende y se apaga, y publica el
  patrón ``Toggle``: se le pregunta directamente.
* **ChatGPT** cambia de botones. Con el micrófono parado enseña «Dictar»; en
  cuanto empieza, ese desaparece y salen «Detener dictado», «Transcribir y
  enviar» y «Cancelar dictado». Así que el estado se lee por lo que hay en
  pantalla, y encima sale gratis algo que nosotros hacíamos a mano: para la
  palanca arriba está su propio «Transcribir y enviar», que es exactamente eso
  y lo hace él.

Si un programa no tiene dictado propio —o le cambia el nombre a los botones—
queda Win+H, que funciona en cualquier sitio aunque sea a ciegas. Por eso esto
no sustituye al otro, se antepone.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from .cuadro_de_texto import _automatizacion, _despertar_accesibilidad, hay_soporte
from .registro import obtener

_log = obtener("microfono")

#: Identificadores de los patrones de la capa de accesibilidad que se usan.
PATRON_INVOKE = 10000
PATRON_TOGGLE = 10015

#: Tipo de control «botón».
TIPO_BOTON = 50000

#: Lo que tarda la interfaz en reflejar el cambio. Preguntar antes de esto
#: devuelve el estado viejo — comprobado: tras pulsar el botón de Claude seguía
#: diciendo «grabando» hasta pasado un momento, y parecía que no había obedecido.
ESPERA_DEL_ESTADO_S = 1.2

#: Cuánto se le da como mucho a la interfaz para reflejar lo que se le pidió.
#: ChatGPT transcribe antes de soltar sus botones de dictado y eso no es
#: instantáneo; con una espera fija se leía «sigue grabando» tras pararlo.
ESPERA_MAXIMA_S = 4.0

#: Cómo habla cada programa.
#:
#: Los nombres se buscan en minúsculas y por trozos, y van en varios idiomas
#: porque la aplicación se pone en el del sistema y eso no lo controlamos: el
#: mismo botón es «Dictar» o «Dictate».
PERFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "claude": {
        # Un solo botón que se enciende y se apaga... **y se renombra**: en
        # reposo es «Mantén presionado para grabar» y mientras graba pasa a
        # llamarse «Detener dictado». Si solo se busca el primer nombre, en
        # cuanto empieza a grabar deja de encontrarse y parece que el programa
        # no tiene dictado. Hay que conocer los dos.
        "interruptor": (
            "grabar", "record", "detener dictado", "stop dictation",
        ),
        # Y en otras versiones de Claude (vista el 4/9/2026 en otro PC) no hay
        # interruptor: hay un botón «Dictar» normal, como en ChatGPT, que al
        # grabar se cambia por «Detener dictado». Si no aparece el interruptor
        # se cae a esto. «Entrada de voz» es el modo de voz, no el dictado.
        "empezar": ("dictar", "dictate", "grabar", "record"),
        "parar": ("detener dictado", "stop dictation"),
    },
    "chatgpt": {
        # Su atajo, de respaldo por si algún día no se encuentra el botón.
        # No va primero: un atajo necesita la ventana al frente y el botón no.
        "atajo": "ctrl+shift+d",
        "empezar": ("dictar", "dictate"),
        "parar": ("detener dictado", "stop dictation"),
        "enviar": ("transcribir y enviar", "transcribe and send"),
        "cancelar": ("cancelar dictado", "cancel dictation"),
    },
}

#: Para lo que no esté descrito, se prueba lo más común.
PERFIL_POR_OMISION = {
    "empezar": ("dictar", "dictate", "grabar", "record"),
    "parar": ("detener dictado", "stop dictation"),
}


def perfil_de(programa: str) -> dict[str, tuple[str, ...]]:
    bajo = (programa or "").lower()
    for clave, perfil in PERFILES.items():
        if clave in bajo:
            return perfil
    return PERFIL_POR_OMISION


def _botones(hwnd: int) -> list[Any]:
    """Todos los botones de la ventana, o una lista vacía si no se puede."""
    if not hay_soporte():
        return []
    try:
        uia, UIA = _automatizacion()
    except Exception:  # noqa: BLE001 - sin la biblioteca no hay nada que hacer
        _log.debug("No se pudo abrir la automatización de interfaz", exc_info=True)
        return []
    _despertar_accesibilidad(hwnd)
    try:
        raiz = uia.ElementFromHandle(hwnd)
        condicion = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, TIPO_BOTON)
        hallados = raiz.FindAll(UIA.TreeScope_Descendants, condicion)
        return [hallados.GetElement(i) for i in range(hallados.Length)]
    except Exception:  # noqa: BLE001 - la ventana puede irse mientras se mira
        _log.debug("Fallo mirando los botones de la ventana", exc_info=True)
        return []


def _coincide(nombre: str, trozos: tuple[str, ...]) -> bool:
    """¿El nombre lleva alguno de los trozos como palabra entera?

    Por subcadena no vale: «record» (el botón de Claude en inglés) está dentro
    de «**Record**ado una memoria…», que es como Claude resume una sesión en su
    barra lateral. Ese botón aparece antes que el del micrófono, no tiene
    interruptor, y con él elegido el dictado caía a Win+H sin decir por qué.
    """
    bajo = (nombre or "").strip().lower()
    if not bajo:
        return False
    return any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", bajo) for t in trozos)


def _coincidentes(botones: list[Any], trozos: tuple[str, ...]) -> list[Any]:
    hallados = []
    for elemento in botones:
        try:
            nombre = elemento.CurrentName or ""
        except Exception:  # noqa: BLE001
            continue
        if _coincide(nombre, trozos):
            hallados.append(elemento)
    return hallados


def _buscar(botones: list[Any], trozos: tuple[str, ...]) -> Optional[Any]:
    hallados = _coincidentes(botones, trozos)
    return hallados[0] if hallados else None


def _buscar_interruptor(botones: list[Any], trozos: tuple[str, ...], interruptor_de=None) -> tuple[Any, Any]:
    """El primer botón que coincide **y tiene interruptor**, con su interruptor.

    Puede haber varios botones con el nombre parecido; el que interesa es el
    que se puede encender y apagar. Devuelve ``(None, None)`` si no hay.
    """
    interruptor_de = interruptor_de or _interruptor
    for boton in _coincidentes(botones, trozos):
        interruptor = interruptor_de(boton)
        if interruptor is not None:
            return boton, interruptor
    return None, None


def _interruptor(boton: Any):
    """El interruptor de un botón, o ``None`` si ese botón no tiene.

    No basta con mirar si ``GetCurrentPattern`` devuelve algo: cuando el
    elemento no admite el patrón devuelve un **puntero nulo**, que en Python no
    es ``None`` y pasa cualquier comprobación ingenua. El fallo aparece después,
    al usarlo, con un «NULL COM pointer access» que no dice de dónde viene.
    """
    try:
        _, UIA = _automatizacion()
        crudo = boton.GetCurrentPattern(PATRON_TOGGLE)
        if not crudo:
            return None
        return crudo.QueryInterface(UIA.IUIAutomationTogglePattern)
    except Exception:  # noqa: BLE001
        return None


#: Cómo se escribe cada tecla de un atajo, en códigos de Windows.
_TECLAS = {
    "ctrl": 0x11, "control": 0x11,
    "shift": 0x10, "may": 0x10, "mayus": 0x10,
    "alt": 0x12, "win": 0x5B,
}


def _mandar_atajo(atajo: str) -> bool:
    """Manda una combinación de teclas a la ventana que esté delante.

    Se importa aquí dentro y no arriba porque ``dictado`` ya importa este
    módulo: hacerlo al revés en la cabecera cerraría el círculo.
    """
    from .dictado import _pulsar as pulsar_teclas
    from .dictado import _soltar_modificadores

    codigos = []
    for parte in atajo.lower().split("+"):
        parte = parte.strip()
        if not parte:
            continue
        if parte in _TECLAS:
            codigos.append(_TECLAS[parte])
        elif len(parte) == 1:
            codigos.append(ord(parte.upper()))
        else:
            _log.debug("No sé escribir la tecla «%s» del atajo «%s»", parte, atajo)
            return False
    if not codigos:
        return False
    # Sin esto el atajo llega contaminado con lo que la persona tenga pulsado.
    _soltar_modificadores()
    time.sleep(0.05)
    return pulsar_teclas(*codigos) > 0


def _pulsar(boton: Any) -> bool:
    """Pulsa un botón por accesibilidad. Devuelve si se pudo."""
    try:
        _, UIA = _automatizacion()
        crudo = boton.GetCurrentPattern(PATRON_INVOKE)
        if not crudo:
            return False
        crudo.QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
        return True
    except Exception:  # noqa: BLE001 - el botón puede irse mientras se pulsa
        _log.debug("El botón no aceptó la pulsación", exc_info=True)
        return False


class MicrofonoDeLaApp:
    """El dictado de un programa concreto, leído y manejado por accesibilidad."""

    def __init__(self, hwnd: int, programa: str) -> None:
        self.hwnd = hwnd
        self.programa = programa
        self.perfil = perfil_de(programa)

    # --- lectura ------------------------------------------------------
    def estado(self, intentos: int = 2) -> Optional[bool]:
        """¿Está grabando? ``None`` si este programa no lo cuenta.

        Devolver ``None`` es importante: significa «no lo sé», y quien llama
        debe entonces irse a Win+H en vez de inventarse una respuesta. Adivinar
        aquí sería repetir el error que se viene a corregir.

        Se pregunta dos veces porque estas aplicaciones son Chromium por
        dentro y su árbol tarda un instante en reasentarse cuando los botones
        acaban de cambiar —justo después de arrancar o parar el dictado, que es
        cuando más falta hace leerlo—. Una sola lectura ahí devuelve vacío y
        parece que el programa se quedó sin dictado.
        """
        for intento in range(max(1, intentos)):
            leido = self._leer_estado()
            if leido is not None:
                return leido
            if intento < intentos - 1:
                time.sleep(0.35)
        return None

    def _leer_estado(self) -> Optional[bool]:
        botones = self._botones()
        if not botones:
            return None

        trozos = self.perfil.get("interruptor")
        if trozos:
            _, interruptor = _buscar_interruptor(botones, trozos)
            if interruptor is not None:
                try:
                    return bool(interruptor.CurrentToggleState == 1)
                except Exception:  # noqa: BLE001
                    return None
            # Sin interruptor se sigue abajo, por presencia, si el perfil lo describe.

        # Por presencia: si está el botón de parar, es que está grabando.
        if _buscar(botones, self.perfil.get("parar", ())) is not None:
            return True
        if _buscar(botones, self.perfil.get("empezar", ())) is not None:
            return False
        return None

    def hay_dictado(self) -> bool:
        """¿Este programa publica un dictado que sepamos manejar?"""
        return self.estado() is not None

    # --- mando --------------------------------------------------------
    def arrancar(self) -> Optional[bool]:
        """Pone a grabar. Si ya estaba, no toca nada."""
        actual = self.estado()
        if actual is None or actual:
            return actual
        return self._accionar("empezar", quedando=True)

    def parar(self, enviar: bool = False) -> Optional[bool]:
        """Deja de grabar. Con ``enviar``, además manda lo dictado.

        Cuando el programa tiene su propio «transcribir y enviar» se usa ese,
        que es más fiable que dictar, cerrar y pulsar Intro por nuestra cuenta:
        lo hace él, sabiendo cuándo ha terminado de transcribir.
        """
        actual = self.estado()
        if actual is None or not actual:
            return actual
        if enviar and self.perfil.get("enviar"):
            return self._accionar("enviar", quedando=False)
        return self._accionar("parar", quedando=False)

    def puede_enviar_el_solo(self) -> bool:
        """¿Trae su propio «transcribir y enviar»?"""
        return bool(self.perfil.get("enviar")) and self.estado() is not None

    # --- interior -----------------------------------------------------
    def _botones(self) -> list[Any]:
        return _botones(self.hwnd)

    def _accionar(self, papel: str, quedando: bool) -> Optional[bool]:
        botones = self._botones()
        trozos = self.perfil.get("interruptor")
        interruptor = None
        if trozos:
            # Un solo botón para las dos cosas.
            _, interruptor = _buscar_interruptor(botones, trozos)
        if interruptor is not None:
            try:
                interruptor.Toggle()
            except Exception:  # noqa: BLE001
                _log.debug("El interruptor no aceptó la pulsación", exc_info=True)
                return None
        else:
            # **El botón primero, el atajo de respaldo.** Parece al revés de lo
            # que uno esperaría, y hay una razón medida: pulsar un botón por
            # accesibilidad no necesita que la ventana esté al frente, y un
            # atajo de teclado sí. Nosotros enfocamos el cuadro de escribir por
            # accesibilidad, que no siempre trae la ventana adelante, así que
            # el atajo se iba a cualquier otro sitio y ChatGPT no arrancaba
            # nunca —quedaba «parado» en el registro después de pedirle que
            # grabara—. El botón, en cambio, va directo al programa.
            boton = _buscar(botones, self.perfil.get(papel, ()))
            if boton is None or not _pulsar(boton):
                atajo = self.perfil.get("atajo")
                if not atajo or papel not in ("empezar", "parar"):
                    return None
                if not _mandar_atajo(atajo):
                    return None
        # Se espera a que el estado cuadre, en vez de un rato fijo. ChatGPT
        # tarda lo que tarde en transcribir antes de soltar sus botones de
        # dictado, y con una espera fija se leía «sigue grabando» justo después
        # de pararlo — y entonces la pulsación siguiente intentaba pararlo otra
        # vez en lugar de arrancarlo.
        limite = time.monotonic() + ESPERA_MAXIMA_S
        leido = None
        while time.monotonic() < limite:
            time.sleep(0.25)
            leido = self.estado(intentos=1)
            if leido == quedando:
                return leido
        return quedando if leido is None else leido


def buscar(hwnd: int, programa: str) -> Optional["MicrofonoDeLaApp"]:
    """El dictado propio de esa ventana, si lo hay y lo entendemos."""
    if not hwnd or not hay_soporte():
        return None
    micro = MicrofonoDeLaApp(hwnd, programa)
    return micro if micro.hay_dictado() else None


__all__ = ["MicrofonoDeLaApp", "buscar", "perfil_de", "PERFILES"]
