"""Que la tecla del micrófono haga lo que uno espera que haga.

Pulsar el micrófono debería abrir el dictado **dentro del programa con el que
estás hablando**, y eso el teclado no lo puede hacer solo: un teclado manda
teclas, no sabe qué ventana tienes delante ni puede traerla al frente.

Mandar directamente Win+H tampoco basta, y por dos motivos que se notan enseguida:

* El dictado de Windows escribe donde esté el foco. Si el foco está en otra
  ventana —o en la propia ventana pero fuera del cuadro de texto— lo dictado se
  va a cualquier parte.
* Win+H es un interruptor: si el dictado ya estaba abierto, lo cierra. De ahí la
  sensación de que «a veces no se activa el micrófono»; se activaba y se
  apagaba en la misma pulsación.

Así que la tecla no manda Win+H: manda una combinación que no usa nadie más y
que este módulo escucha. Al recibirla, trae al frente el programa que manda en
el modo activo, espera a que el sistema termine el cambio de ventana, y solo
entonces abre el dictado.

Solo tiene sentido en Windows; en los demás sistemas se queda quieto.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import os
import time
from ctypes import wintypes
from typing import Callable, Optional

from .registro import obtener

_log = obtener("dictado")

#: La combinación que manda la tecla del micrófono. Lleva tres modificadores y
#: una tecla que ningún programa usa, para no pisarle el atajo a nadie.
ATAJO_DICTADO = "ctrl+alt+may+f13"

#: Dos pulsaciones más juntas que esto son la misma. Ni el dedo más rápido abre
#: y cierra el dictado en medio segundo.
REBOTE_S = 1.0

# --- constantes de Windows ---------------------------------------------------
MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x0001, 0x0002, 0x0004
MOD_NOREPEAT = 0x4000
VK_F13, VK_H, VK_LWIN = 0x7C, 0x48, 0x5B

#: Los modificadores que hay que soltar antes de abrir el dictado. Cuando llega
#: la combinación, el teclado todavía los tiene pulsados: si no se sueltan,
#: Windows recibe Ctrl+Alt+Mayús+Win+H, que no es el atajo del dictado y no hace
#: absolutamente nada. Es la causa de «a veces no se activa el micrófono».
MODIFICADORES_A_SOLTAR = (
    0x11,  # Ctrl
    0xA2, 0xA3,  # Ctrl izquierdo y derecho
    0x12,  # Alt
    0xA4, 0xA5,  # Alt izquierdo y derecho
    0x10,  # Mayús
    0xA0, 0xA1,  # Mayús izquierdo y derecho
    0x5B, 0x5C,  # Win izquierdo y derecho
)
WM_HOTKEY = 0x0312
ENTRADA_TECLADO = 1
TECLA_SOLTAR = 0x0002
TECLA_EXTENDIDA = 0x0001

#: Cuánto se espera a que Windows termine de cambiar de ventana antes de abrir
#: el dictado. Por debajo de esto, el dictado se abre sobre la ventana anterior.
ESPERA_FOCO_S = 0.35


def _hacerse_consciente_del_escalado() -> None:
    """Que las coordenadas signifiquen lo mismo al leerlas y al usarlas.

    Con el escalado de Windows al 125 % o 150 % —lo normal en portátiles y en
    pantallas 4K—, un proceso que no se declara consciente del DPI recibe
    coordenadas «virtuales» de ``GetWindowRect`` pero ``SetCursorPos`` las
    interpreta como físicas. El clic acaba desplazado, y cuanto mayor es el
    escalado, más lejos. Declararse consciente por monitor arregla las dos
    puntas a la vez y hace que esto funcione igual en cualquier pantalla.

    Se intenta la forma moderna y se cae a la antigua; si el proceso ya venía
    declarado, Windows contesta que no y no pasa nada.
    """
    if os.name != "nt":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        # -4 = PER_MONITOR_AWARE_V2, la buena con varios monitores distintos.
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:  # noqa: BLE001 - en Windows viejos no existe; no es grave
        try:
            ctypes.WinDLL("user32").SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


_hacerse_consciente_del_escalado()


def hay_soporte() -> bool:
    return os.name == "nt"


# --- envío de teclas ---------------------------------------------------------
# Ojo con estas estructuras: ``SendInput`` comprueba el tamaño que se le declara
# y, si no cuadra al byte, **no inyecta nada y devuelve cero sin dar error**. La
# unión tiene que llevar los tres tipos de entrada aunque solo usemos el teclado,
# porque el mayor de ellos —el del ratón— es el que fija el tamaño: 40 bytes en
# 64 bits. Con la unión recortada salían 32 y no funcionaba nada.

_PUNTERO = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _TECLA(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _PUNTERO),
    ]


class _RATON(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _PUNTERO),
    ]


class _APARATO(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _UNION(ctypes.Union):
    _fields_ = [("ki", _TECLA), ("mi", _RATON), ("hi", _APARATO)]


class _ENTRADA(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


def _api():
    """user32 con las firmas declaradas, que si no ctypes convierte de más."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_ENTRADA), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    user32.MapVirtualKeyW.restype = wintypes.UINT
    return user32


def _evento(user32, vk: int, soltar: bool = False) -> _ENTRADA:
    """Un evento de tecla, con su código de barrido.

    El código de barrido no es adorno: algunos atajos del sistema —Win+H entre
    ellos— no reaccionan a un evento que solo lleva el código virtual.
    """
    banderas = TECLA_SOLTAR if soltar else 0
    if vk in (VK_LWIN, 0x5C):
        banderas |= TECLA_EXTENDIDA
    escaneo = user32.MapVirtualKeyW(vk, 0)
    return _ENTRADA(ENTRADA_TECLADO, _UNION(ki=_TECLA(vk, escaneo, banderas, 0, 0)))


def _pulsar(*codigos: int) -> int:
    """Pulsa y suelta una combinación. Devuelve cuántos eventos entraron."""
    user32 = _api()
    eventos = [_evento(user32, c) for c in codigos]
    eventos += [_evento(user32, c, soltar=True) for c in reversed(codigos)]
    lote = (_ENTRADA * len(eventos))(*eventos)
    entraron = user32.SendInput(len(eventos), lote, ctypes.sizeof(_ENTRADA))
    if entraron != len(eventos):
        _log.warning(
            "Windows solo aceptó %s de %s pulsaciones (error %s). Suele ser que "
            "la ventana de delante corre con más privilegios que nosotros.",
            entraron, len(eventos), ctypes.get_last_error(),
        )
    return entraron


def _soltar_modificadores() -> None:
    """Suelta las teclas que el usuario aún tiene pulsadas.

    Sin esto, el atajo que se manda a continuación llega contaminado con los
    modificadores de la combinación que nos despertó, y Windows lo descarta.
    """
    user32 = _api()
    eventos = [_evento(user32, c, soltar=True) for c in MODIFICADORES_A_SOLTAR]
    lote = (_ENTRADA * len(eventos))(*eventos)
    user32.SendInput(len(eventos), lote, ctypes.sizeof(_ENTRADA))


def dictado_configurado() -> bool:
    """Ya no se intenta adivinar: siempre dice que sí.

    Hubo aquí una comprobación por el registro que resultó ser mentira. Decía
    que el dictado no estaba activado en equipos donde funcionaba perfectamente
    —las claves que miraba solo aparecen si se han tocado ciertos ajustes— y el
    resultado era un aviso alarmante y falso en la cara de quien lo usaba.

    Se deja la función para no romper a quien la llame, pero sin inventar: si el
    dictado no se abre, lo verá la persona antes que nosotros.
    """
    return True


def _dictado_configurado_por_registro() -> bool:
    """La comprobación vieja, guardada como aviso para futuras tentaciones.

    La primera vez, Windows pide aceptar el reconocimiento de voz en línea y no
    abre nada hasta que se acepta. Mientras tanto, Win+H no da error: sencilla-
    mente no pasa nada, que es lo más desconcertante que puede pasar. Detectarlo
    permite decirlo con todas las letras en vez de dejar a la persona pulsando
    una tecla que parece rota.
    """
    if not hay_soporte():
        return False
    import winreg

    for rama, camino in (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Speech_OneCore\Settings"
                                   r"\OnlineSpeechPrivacy"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion"
                                   r"\Speech_OneCore\Settings\VoiceTyping"),
    ):
        try:
            with winreg.OpenKey(rama, camino):
                return True
        except OSError:
            continue
    return False


AVISO_SIN_DICTADO = (
    "El dictado de Windows no está activado en este equipo, así que Win+H no "
    "abre nada. Pulsa Win+H tú una vez y acepta lo que te pregunte, o ve a "
    "Configuración › Privacidad y seguridad › Voz y enciende el reconocimiento "
    "de voz en línea. Es cosa de una vez."
)


def abrir_dictado() -> None:
    """Win+H, el dictado de Windows, con la mesa despejada."""
    _soltar_modificadores()
    time.sleep(0.06)  # que Windows procese el soltar antes del atajo
    _pulsar(VK_LWIN, VK_H)


def cerrar_dictado() -> None:
    """Cierra el dictado con Escape, no con Win+H.

    Win+H es un interruptor, y desde fuera no hay forma de saber en qué posición
    está: el panel de dictado no aparece como ventana ni se asoma a la capa de
    accesibilidad, se buscó y no está. Así que si Windows lo había cerrado solo
    —se cierra tras un silencio— el Win+H de «cerrar» lo volvía a abrir. Ese era
    el «se activa cuando lo cierro».

    Escape no tiene ese problema: cierra el dictado si está abierto y no hace
    nada si no lo está. Deja el cursor donde estaba, así que lo dictado sigue en
    el cuadro listo para enviarse.
    """
    _soltar_modificadores()
    time.sleep(0.06)
    _pulsar(VK_ESC)


# --- traer una ventana al frente ---------------------------------------------
def enfocar(proceso: str) -> bool:
    """Trae al frente la ventana principal de ese programa.

    Windows no deja que un proceso cualquiera robe el foco: ``SetForegroundWindow``
    falla en silencio salvo que quien llama sea ya el proceso de primer plano.
    El rodeo conocido es engancharse a la cola de entrada de ese proceso durante
    un instante; entonces el sistema lo trata como si el cambio lo hubiera pedido
    la propia aplicación.
    """
    if not hay_soporte() or not proceso:
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    objetivo: list[int] = []
    proceso = proceso.lower().removesuffix(".exe")

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def mirar(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        manejador = kernel32.OpenProcess(0x1000, False, pid.value)
        if not manejador:
            return True
        try:
            tamano = wintypes.DWORD(1024)
            memoria = ctypes.create_unicode_buffer(tamano.value)
            if kernel32.QueryFullProcessImageNameW(
                manejador, 0, memoria, ctypes.byref(tamano)
            ):
                nombre = memoria.value.rsplit("\\", 1)[-1].lower().removesuffix(".exe")
                if nombre == proceso:
                    objetivo.append(hwnd)
        finally:
            kernel32.CloseHandle(manejador)
        return True

    user32.EnumWindows(mirar, 0)
    if not objetivo:
        _log.info("No hay ninguna ventana de «%s» abierta", proceso)
        return False

    hwnd = _la_principal(objetivo)
    # Restaurar sin preguntar. Un programa guardado en la bandeja no siempre se
    # declara «minimizado»: Electron lo aparca fuera de la pantalla, con lo que
    # IsIconic dice que no y la ventana sigue midiendo 158x26 en coordenadas
    # negativas. Medirla ahí manda el clic a veinte mil píxeles de la nada.
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

    delante = user32.GetForegroundWindow()
    hilo_actual = kernel32.GetCurrentThreadId()
    hilo_delante = user32.GetWindowThreadProcessId(delante, None)
    enganchado = False
    if hilo_delante and hilo_delante != hilo_actual:
        enganchado = bool(user32.AttachThreadInput(hilo_delante, hilo_actual, True))
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if enganchado:
            user32.AttachThreadInput(hilo_delante, hilo_actual, False)
    return user32.GetForegroundWindow() == hwnd


def _rectangulo(hwnd) -> tuple[int, int, int, int]:
    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    r = _RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", ctypes.c_long * 4),
    ]


def hay_cursor_de_escritura() -> bool:
    """¿Hay un cursor parpadeando en algún cuadro de texto?

    Es la única forma honesta de saber si el clic acertó. Windows lo cuenta en
    ``GetGUIThreadInfo``: si hay ``hwndCaret``, hay dónde escribir. Sin esta
    comprobación uno adivina la altura del cuadro y reza, que es lo que estaba
    haciendo.
    """
    if not hay_soporte():
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = user32.GetForegroundWindow()
    hilo = user32.GetWindowThreadProcessId(hwnd, None)
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    if not user32.GetGUIThreadInfo(hilo, ctypes.byref(info)):
        return False
    # 0x00000001 = GUI_CARETBLINKING
    return bool(info.hwndCaret) or bool(info.flags & 0x00000001)


def _clic(x: int, y: int) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class _PUNTO(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    antes = _PUNTO()
    user32.GetCursorPos(ctypes.byref(antes))
    try:
        user32.SetCursorPos(x, y)
        time.sleep(0.05)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.18)
    finally:
        user32.SetCursorPos(antes.x, antes.y)


#: Dónde cae el clic, como fracción del alto de la ventana medida desde abajo.
#: En ChatGPT y en Claude el cuadro de escribir está en esa banda; si en algún
#: programa cae mal, se ajusta por modo con «alto_cuadro».
FRACCION_DEL_CUADRO = 0.10


def poner_el_cursor_en_el_prompt(hwnd, alto_del_cuadro: int = 0) -> bool:
    """Hace clic en el cuadro de escribir y devuelve el ratón a su sitio.

    El dictado de Windows escribe donde esté el cursor de texto, no donde esté
    la ventana. Traerla al frente no basta: si el cuadro no tiene el foco, lo
    dictado se pierde.

    No hay forma limpia de pedirle a otra aplicación «pon el foco en tu cuadro
    de texto»: ChatGPT y Claude son ventanas web dentro de un envoltorio y no
    exponen sus campos al sistema —tampoco se puede comprobar si el clic acertó,
    porque Chromium dibuja su propio cursor y Windows no lo ve—. Así que se hace
    lo que haría una persona: un clic donde está el cuadro, y el ratón de vuelta
    a donde estaba para no dejarlo movido.
    """
    if not hay_soporte():
        return False
    izquierda, arriba, derecha, abajo = _rectangulo(hwnd)
    ancho, alto = derecha - izquierda, abajo - arriba
    if ancho < 200 or alto < 200:
        return False

    # La posición se calcula en proporción al alto de la ventana, no en píxeles
    # fijos: así cae en el mismo sitio con cualquier resolución y con la ventana
    # a cualquier tamaño.
    margen = alto_del_cuadro or int(alto * FRACCION_DEL_CUADRO)
    x = (izquierda + derecha) // 2
    y = abajo - margen
    # Por si acaso: nunca fuera de la ventana ni fuera del borde de la pantalla.
    y = max(arriba + 40, min(y, abajo - 20))
    x = max(izquierda + 20, min(x, derecha - 20))

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class _PUNTO(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    antes = _PUNTO()
    user32.GetCursorPos(ctypes.byref(antes))
    try:
        user32.SetCursorPos(x, y)
        time.sleep(0.05)
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # botón izquierdo abajo
        time.sleep(0.03)
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # y arriba
        time.sleep(0.18)
    finally:
        user32.SetCursorPos(antes.x, antes.y)
    _log.debug("Clic en el cuadro a %s px del borde inferior", margen)
    return True


def _ventana_de(proceso: str):
    """El identificador de la ventana principal de ese programa, si la hay."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    objetivo: list[int] = []
    proceso = proceso.lower().removesuffix(".exe")

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def mirar(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        manejador = kernel32.OpenProcess(0x1000, False, pid.value)
        if not manejador:
            return True
        try:
            tamano = wintypes.DWORD(1024)
            memoria = ctypes.create_unicode_buffer(tamano.value)
            if kernel32.QueryFullProcessImageNameW(
                manejador, 0, memoria, ctypes.byref(tamano)
            ):
                nombre = memoria.value.rsplit("\\", 1)[-1].lower().removesuffix(".exe")
                if nombre == proceso:
                    objetivo.append(hwnd)
        finally:
            kernel32.CloseHandle(manejador)
        return True

    user32.EnumWindows(mirar, 0)
    return _la_principal(objetivo)


def _esperar_a_que_se_asiente(proceso: str, plazo_s: float = 1.5) -> bool:
    """Espera a que la ventana tenga un tamaño y una posición creíbles.

    Restaurar una ventana no es instantáneo, y medirla a media animación da
    números que no sirven. Se espera a que ocupe algo y esté dentro de la
    pantalla, o hasta que se acabe el plazo.
    """
    limite = time.monotonic() + plazo_s
    while time.monotonic() < limite:
        hwnd = _ventana_de(proceso)
        if hwnd:
            izquierda, arriba, derecha, abajo = _rectangulo(hwnd)
            if derecha - izquierda > 300 and abajo - arriba > 300 and derecha > 0 and abajo > 0:
                return True
        time.sleep(0.15)
    return False


def _la_principal(ventanas: list) -> Optional[int]:
    """De todas las ventanas de un programa, la que de verdad usa la persona.

    Un programa moderno tiene varias: la del icono de la bandeja, alguna oculta
    fuera de pantalla, ventanas de apoyo. ChatGPT tiene una de 158x26 colocada en
    coordenadas negativas, y quedarse con la primera que aparece —como se hacía—
    mandaba el clic a veinte mil píxeles fuera de la pantalla. La buena es la
    más grande.
    """
    if not ventanas:
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    def superficie(hwnd) -> int:
        izquierda, arriba, derecha, abajo = _rectangulo(hwnd)
        ancho, alto = derecha - izquierda, abajo - arriba
        if ancho <= 0 or alto <= 0:
            return 0
        return ancho * alto

    return max(ventanas, key=superficie)


def abrir_programa(orden: str) -> bool:
    """Arranca un programa que no estaba abierto.

    Las aplicaciones de la Tienda no tienen una ruta que se pueda ejecutar: se
    abren por su identificador, y de eso se encarga el explorador.
    """
    if not orden or not hay_soporte():
        return False
    import subprocess

    try:
        if orden.lower().startswith("shell:"):
            subprocess.Popen(["explorer.exe", orden], shell=False)
        else:
            subprocess.Popen(orden, shell=True)
    except Exception:  # noqa: BLE001 - que no arranque no debe tumbar nada
        _log.exception("No se pudo abrir «%s»", orden)
        return False
    return True


VK_INTRO = 0x0D
VK_ESC = 0x1B


class Dictado:
    """Lleva la cuenta de si el micrófono está abierto o cerrado.

    Win+H es un interruptor, así que la tecla tiene que comportarse como tal:
    la primera pulsación abre y la segunda cierra. Sin recordar en cuál de los
    dos estados estamos, la segunda pulsación volvería a enfocar la ventana y a
    pinchar el cuadro —molesto y desconcertante— además de cerrar el dictado.
    """

    def __init__(self) -> None:
        self.abierto = False
        #: ¿Es la primera apertura desde que arrancó el servicio?
        #:
        #: Importa porque **el dictado de Windows sobrevive a nuestros
        #: reinicios y nuestra memoria no**. Si el servicio se reinicia con el
        #: panel de dictado abierto, arrancamos creyendo que está cerrado, y la
        #: primera pulsación manda Win+H —que es un interruptor— y lo cierra en
        #: vez de abrirlo. De ahí el «la primera vez que lo pulso no se
        #: activa», que después ya va bien porque las cuentas vuelven a cuadrar.
        self._primera_vez = True
        self.programa = ""
        self._ultima = 0.0

    def _asegurar_punto_de_partida(self) -> None:
        """Deja el dictado cerrado la primera vez, para poder abrirlo de veras.

        No se puede preguntar a Windows si su panel está abierto —no es una
        ventana ni se asoma a la capa de accesibilidad, se buscó y no está—,
        así que en vez de averiguarlo se impone: Escape cierra el dictado si
        estaba abierto y no hace nada si no. A partir de ahí, abrir es abrir.
        """
        if not self._primera_vez:
            return
        self._primera_vez = False
        cerrar_dictado()
        time.sleep(0.25)

    def abrir_solo(
        self,
        programa: str = "",
        lanzar: str = "",
        pinchar_el_cuadro: bool = True,
        alto_del_cuadro: int = 0,
    ) -> dict:
        """Abre el dictado si estaba cerrado; si ya estaba abierto, no toca nada.

        Lo usa el modo manos libres. Tiene que ser abrir y no alternar: quien
        llama aquí no es tu dedo sino un agente que acaba de terminar, y si
        alternara podría cerrarte el micrófono justo mientras hablas.
        """
        if self.abierto:
            return {"accion": "ya estaba", "programa": self.programa}
        self._ultima = time.monotonic()
        self._asegurar_punto_de_partida()
        hecho = dictar_en(
            programa, lanzar,
            pinchar_el_cuadro=pinchar_el_cuadro,
            alto_del_cuadro=alto_del_cuadro,
        )
        self.abierto = True
        self.programa = programa
        return {"accion": "abierto", **hecho}

    def alternar(
        self,
        programa: str = "",
        lanzar: str = "",
        pinchar_el_cuadro: bool = True,
        enviar_al_cerrar: bool = False,
        alto_del_cuadro: int = 0,
    ) -> dict:
        """Abre el dictado, o lo cierra si ya estaba abierto."""
        # Antirrebote. La combinación llega dos veces por pulsación —el teclado
        # la manda al pulsar y al soltar—, y sin esto la segunda deshacía la
        # primera al instante: cerrabas el micrófono y se volvía a abrir.
        ahora = time.monotonic()
        if ahora - self._ultima < REBOTE_S:
            _log.info("Pulsación repetida a los %.2f s: se ignora", ahora - self._ultima)
            return {"accion": "repetida", "programa": self.programa}
        self._ultima = ahora

        if self.abierto:
            enviado = False
            if enviar_al_cerrar:
                # Con la palanca arriba se envía PRIMERO y se cierra después.
                # El orden importa: cerrar antes puede quitarle el foco al
                # cuadro, y entonces el Intro no llega a ninguna parte y lo
                # dictado se queda escrito sin mandar.
                time.sleep(0.5)   # que el dictado termine de escribir
                _pulsar(VK_INTRO)
                enviado = True
                time.sleep(0.25)
            cerrar_dictado()
            self.abierto = False
            return {"accion": "cerrado", "programa": self.programa, "enviado": enviado}

        self._asegurar_punto_de_partida()
        hecho = dictar_en(
            programa,
            lanzar,
            pinchar_el_cuadro=pinchar_el_cuadro,
            alto_del_cuadro=alto_del_cuadro,
        )
        self.abierto = True
        self.programa = programa
        return {"accion": "abierto", **hecho}


def dictar_en(
    proceso: str,
    lanzar: str = "",
    espera_arranque_s: float = 6.0,
    pinchar_el_cuadro: bool = True,
    alto_del_cuadro: int = 0,
) -> dict:
    """Enfoca el programa —abriéndolo si hace falta— y dicta dentro de él."""
    if not proceso:
        time.sleep(ESPERA_FOCO_S)
        abrir_dictado()
        return {"programa": "", "enfocado": False, "abierto": False}

    enfocado = enfocar(proceso)
    abierto = False
    if not enfocado and lanzar:
        # No estaba abierto. Se abre y se espera a que aparezca su ventana:
        # abrir el dictado antes de que exista sería dictar al vacío.
        abierto = abrir_programa(lanzar)
        if abierto:
            _log.info("Abriendo «%s» para dictar", proceso)
            limite = time.monotonic() + espera_arranque_s
            while time.monotonic() < limite and not enfocado:
                time.sleep(0.4)
                enfocado = enfocar(proceso)

    if not enfocado:
        # Si ya estaba delante, enfocar «falla» porque no había nada que
        # cambiar. Se dicta igual donde esté el foco antes que no hacer nada.
        _log.debug("«%s» no se pudo traer al frente; se dicta donde esté el foco", proceso)

    time.sleep(ESPERA_FOCO_S)
    _esperar_a_que_se_asiente(proceso)

    # El paso que faltaba: poner el cursor en el cuadro de escribir. Sin esto,
    # Windows contesta «selecciona un cuadro de texto» y no dicta nada.
    #
    # Se le pregunta a la capa de accesibilidad, que sabe dónde está el cuadro y
    # deja darle el foco sin tocar el ratón. Adivinar la posición no vale: en
    # ChatGPT el cuadro está a media altura con la conversación vacía y abajo
    # cuando hay mensajes, y en Claude está en otro sitio distinto.
    en_el_cuadro = False
    como = "no"
    if pinchar_el_cuadro:
        hwnd = _ventana_de(proceso)
        if hwnd:
            from .cuadro_de_texto import enfocar_cuadro

            hallado = enfocar_cuadro(hwnd)
            if hallado:
                en_el_cuadro, como = True, hallado.get("nombre") or "por accesibilidad"
            else:
                # Sin accesibilidad queda el clic a ojo: peor, pero mejor que nada.
                en_el_cuadro = poner_el_cursor_en_el_prompt(hwnd, alto_del_cuadro)
                como = "clic a ciegas" if en_el_cuadro else "no"
        time.sleep(0.2)

    abrir_dictado()
    return {
        "programa": proceso,
        "enfocado": enfocado,
        "abierto": abierto,
        "en_el_cuadro": en_el_cuadro,
        "cuadro": como,
    }


# --- escucha de la combinación -----------------------------------------------
class EscuchaDictado:
    """Espera la combinación del micrófono y avisa cuando llega."""

    def __init__(
        self,
        al_pulsar: Callable[[], None],
        identificador: int = 0xA17A,
        tecla_virtual: int = VK_F13,
        nombre: str = ATAJO_DICTADO,
    ) -> None:
        # `tecla_virtual` y `nombre` existen para que otro servicio del mismo
        # PC (MiniMic) escuche su propia combinación: Windows solo deja
        # reservar cada una a un proceso, así que dos teclados no pueden
        # compartir F13.
        self.al_pulsar = al_pulsar
        self.identificador = identificador
        self.tecla_virtual = tecla_virtual
        self.nombre = nombre
        self._parar = False
        self._ultimo_disparo = 0.0

    def correr(self) -> None:
        """Bucle de mensajes. Bloquea: va en su propio hilo."""
        if not hay_soporte():
            _log.info("La tecla del micrófono solo funciona en Windows.")
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        modificadores = MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT

        # Al reiniciar el servicio, Windows tarda un poco en soltar la
        # combinación que tenía reservada el proceso anterior. Rendirse al
        # primer intento dejaba el micrófono muerto hasta el siguiente
        # arranque, que es exactamente lo que pasaba al reiniciar la web.
        reservada = False
        for intento in range(20):
            if user32.RegisterHotKey(None, self.identificador, modificadores, self.tecla_virtual):
                reservada = True
                if intento:
                    _log.info(
                        "La combinación del micrófono se liberó al cabo de %.1f s",
                        intento * 0.5,
                    )
                break
            time.sleep(0.5)
        if not reservada:
            _log.error(
                "No se pudo reservar la combinación del micrófono (%s) en diez "
                "segundos. Suele ser otra copia del servicio todavía viva: "
                "ciérrala y vuelve a arrancar.",
                self.nombre,
            )
            return
        _log.info("Escuchando la tecla del micrófono (%s)", self.nombre)
        try:
            mensaje = wintypes.MSG()
            while not self._parar:
                if user32.GetMessageW(ctypes.byref(mensaje), None, 0, 0) <= 0:
                    break
                if mensaje.message == WM_HOTKEY and mensaje.wParam == self.identificador:
                    ahora = time.monotonic()
                    _log.info(
                        "Combinación recibida (%.2f s desde la anterior)",
                        ahora - self._ultimo_disparo if self._ultimo_disparo else -1,
                    )
                    self._ultimo_disparo = ahora
                    try:
                        self.al_pulsar()
                    except Exception:  # noqa: BLE001 - un fallo no debe callar la tecla
                        _log.exception("Fallo al atender la tecla del micrófono")
        finally:
            user32.UnregisterHotKey(None, self.identificador)

    def parar(self) -> None:
        """Suelta la combinación para que el siguiente arranque la encuentre libre."""
        self._parar = True
        if hay_soporte():
            with contextlib.suppress(Exception):
                ctypes.WinDLL("user32", use_last_error=True).UnregisterHotKey(
                    None, self.identificador
                )
        if hay_soporte():
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW(
                ctypes.WinDLL("kernel32").GetCurrentThreadId(), 0x0012, 0, 0
            )


__all__ = [
    "ATAJO_DICTADO",
    "Dictado",
    "AVISO_SIN_DICTADO",
    "dictado_configurado",
    "MODIFICADORES_A_SOLTAR",
    "abrir_programa",
    "EscuchaDictado",
    "abrir_dictado",
    "cerrar_dictado",
    "dictar_en",
    "FRACCION_DEL_CUADRO",
    "poner_el_cursor_en_el_prompt",
    "enfocar",
    "hay_soporte",
]
