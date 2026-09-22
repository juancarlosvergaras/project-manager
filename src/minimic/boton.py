"""El botón Bluetooth de una tecla (AI_VOICE): reconocerlo y oírlo sin tocarle nada.

Es un aparato Bluetooth **clásico** (chip Jieli) con cuatro caras: un teclado
HID, un control multimedia, una colección de fabricante y un micrófono
**manos libres** (perfil HFP, que Windows enseña como «AI_VOICE Hands-Free»).
El botón manda **Alt derecho** de fábrica, y por Bluetooth no hay manera de
cambiárselo: su herramienta web solo existe para la versión USB (protocolo de
texto por puerto serie: ``PING``, ``KEY_LIST``, ``SET_KEY``…), el canal serie
Bluetooth no contesta, el ``JL_SPP`` devuelve el eco y el informe de
características HID rechaza lectura y escritura (21/9/2026).

Así que no se remapea: **se reconoce**. Windows dice de qué aparato viene cada
pulsación (*Raw Input*), y un Alt derecho que venga del AI_VOICE abre o cierra
el dictado. El AltGr del teclado normal sigue siendo AltGr. Para saber qué
aparato es el AI_VOICE se sube por el árbol de dispositivos: la interfaz HID
→ su padre ``BTHENUM…&<dirección>_C…`` → el nombre que la pila Bluetooth
guarda para esa dirección. Y su micrófono se encuentra por el identificador
de contenedor, como el del teclado de cinco teclas.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

registro = logging.getLogger("minimic.boton")

#: Nombre Bluetooth con el que se vende el aparato.
NOMBRE_DE_FABRICA = "AI_VOICE"
#: Servicio HID de Bluetooth clásico: así empiezan sus rutas HID.
_SERVICIO_HID_BT = "{00001124-0000-1000-8000-00805f9b34fb}"
#: Dos pulsaciones más seguidas que esto son la misma (el botón manda AltGr,
#: que Windows desdobla en Ctrl y Alt derecho).
REBOTE_S = 0.7

WM_INPUT, RIDEV_INPUTSINK, RID_INPUT = 0x00FF, 0x00000100, 0x10000003
RIM_TYPEKEYBOARD = 1
RIDI_DEVICENAME = 0x20000007
WM_QUIT = 0x0012


@dataclass
class Boton:
    nombre: str
    direccion: str = ""             #: 12 hex, mayúsculas, sin separadores
    contenedor: str = ""            #: {GUID} en mayúsculas, como lo da MMDevice
    rutas_hid: list[str] = field(default_factory=list)  #: interfaces HID (teclado) por las que habla
    conectado: bool = True

    @property
    def descripcion(self) -> str:
        return f"{self.nombre} ({self.direccion or '?'})" + ("" if self.conectado else ", no está")


def hay_soporte() -> bool:
    return os.name == "nt"


# --- rutas y árbol de dispositivos ----------------------------------------------

def instancia_de(ruta_hid: str) -> str:
    """``\\\\?\\HID#{…}_LOCALMFG&0002&Col01#8&649811&0&0000#{guid}\\KBD`` →
    ``HID\\{…}_LOCALMFG&0002&Col01\\8&649811&0&0000`` (el identificador PnP)."""
    s = ruta_hid
    if s.startswith("\\\\?\\"):
        s = s[4:]
    corte = s.rfind("#{")
    if corte > 0:
        s = s[:corte]
    return s.replace("#", "\\")


def misma_interfaz(ruta_a: str, ruta_b: str) -> bool:
    """¿Son la misma interfaz HID? Raw Input y hidapi la nombran con distinto
    GUID al final y distinto sufijo; lo que identifica es lo de antes."""
    return instancia_de(ruta_a).lower() == instancia_de(ruta_b).lower()


def direccion_del_padre(identificador_padre: str) -> str:
    """``BTHENUM\\{…}_LOCALMFG&0002\\7&1B9BF59C&0&5BCBA23EA614_C00000000`` → ``5BCBA23EA614``."""
    m = re.search(r"&([0-9A-Fa-f]{12})_C[0-9A-Fa-f]*$", identificador_padre)
    return m.group(1).upper() if m else ""


def _padre_de(identificador: str) -> str:
    """El identificador PnP del padre, por cfgmgr32; «» si no se puede."""
    cm = ctypes.windll.cfgmgr32
    devinst = w.DWORD(0)
    if cm.CM_Locate_DevNodeW(ctypes.byref(devinst), identificador, 0) != 0:
        return ""
    padre = w.DWORD(0)
    if cm.CM_Get_Parent(ctypes.byref(padre), devinst, 0) != 0:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    if cm.CM_Get_Device_IDW(padre, buf, 512, 0) != 0:
        return ""
    return buf.value


def _nombre_bluetooth(direccion: str) -> str:
    """El nombre que la pila Bluetooth de Windows guarda para esa dirección."""
    import winreg

    ruta = rf"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices\{direccion.lower()}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as clave:
            valor, _ = winreg.QueryValueEx(clave, "Name")
    except OSError:
        return ""
    if isinstance(valor, bytes):
        return valor.split(b"\x00", 1)[0].decode("utf-8", "replace")
    return str(valor)


def _contenedor_de(identificador: str) -> str:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Enum\{identificador}") as clave:
            valor, _ = winreg.QueryValueEx(clave, "ContainerID")
            return str(valor).upper()
    except OSError:
        return ""


def buscar(nombre: str = NOMBRE_DE_FABRICA) -> Boton | None:
    """El botón con ese nombre Bluetooth, si está conectado ahora mismo.

    Solo aparece en la lista HID de Windows mientras está conectado, así que
    encontrarlo es saber que está.
    """
    if not hay_soporte() or not nombre:
        return None
    try:
        import hid
        aparatos = hid.enumerate()
    except Exception as e:  # noqa: BLE001 - hidapi da errores variopintos
        registro.debug("botón: no se pudo enumerar HID: %s", e)
        return None
    quiero = nombre.strip().lower()
    encontrado: Boton | None = None
    padres: dict[str, str] = {}
    for a in aparatos:
        ruta = a["path"].decode("utf-8", "replace") if isinstance(a["path"], bytes) else str(a["path"])
        if _SERVICIO_HID_BT not in ruta.lower():
            continue
        if (a.get("usage_page"), a.get("usage")) != (1, 6):
            continue  # solo la cara de teclado
        instancia = instancia_de(ruta)
        padre = padres.get(instancia)
        if padre is None:
            padre = padres[instancia] = _padre_de(instancia)
        direccion = direccion_del_padre(padre)
        if not direccion or _nombre_bluetooth(direccion).strip().lower() != quiero:
            continue
        if encontrado is None:
            encontrado = Boton(nombre=nombre, direccion=direccion, contenedor=_contenedor_de(instancia))
        encontrado.rutas_hid.append(ruta)
    return encontrado


def vigilar(nombre: str, al_cambiar: Callable[[Boton | None], None], cada_s: float = 3.0,
            parar: threading.Event | None = None) -> threading.Thread:
    """Hilo que avisa cuando el botón aparece o desaparece."""
    parar = parar or threading.Event()

    def bucle() -> None:
        ultimo: str | None = None
        while not parar.is_set():
            boton = buscar(nombre)
            firma = boton.direccion if boton else ""
            if ultimo is None or firma != ultimo:
                ultimo = firma
                try:
                    al_cambiar(boton)
                except Exception:  # noqa: BLE001
                    registro.exception("aviso del botón")
            parar.wait(cada_s)

    hilo = threading.Thread(target=bucle, name="minimic-boton-presencia", daemon=True)
    hilo.start()
    return hilo


# --- oír el botón -------------------------------------------------------------------

class Rebote:
    """Decide si una pulsación es nueva o el rebote de la anterior (puro, para probar)."""

    def __init__(self, segundos: float = REBOTE_S) -> None:
        self.segundos = segundos
        self._ultima = 0.0

    def es_nueva(self, ahora: float | None = None) -> bool:
        ahora = time.monotonic() if ahora is None else ahora
        if ahora - self._ultima < self.segundos:
            return False
        self._ultima = ahora
        return True


class EscuchaBoton:
    """Ventana invisible que recibe *Raw Input* de teclado y avisa cuando la
    pulsación viene del botón. Va en su propio hilo (``correr`` bloquea)."""

    def __init__(self, al_pulsar: Callable[[], None]) -> None:
        self.al_pulsar = al_pulsar
        self._rutas: list[str] = []
        self._cerrojo = threading.Lock()
        self._rebote = Rebote()
        self._hilo_id = 0
        self.escuchando = False
        self._nombres: dict[Any, str] = {}
        #: Teclas del botón que siguen apretadas: mantenerlo pulsado hace que
        #: Windows repita la tecla cada pocos ms, y pasado el rebote esas
        #: repeticiones contaban como pulsaciones nuevas (21/9/2026: una
        #: pulsación larga abrió el dictado dos veces).
        self._apretadas: set[int] = set()
        self._atendiendo = threading.Lock()

    def apuntar_a(self, rutas_hid: list[str]) -> None:
        """Las interfaces HID del botón (las de ahora; cambian al reconectar)."""
        with self._cerrojo:
            self._rutas = list(rutas_hid)
            self._nombres.clear()

    def es_del_boton(self, nombre_raw: str) -> bool:
        with self._cerrojo:
            return any(misma_interfaz(nombre_raw, r) for r in self._rutas)

    def parar(self) -> None:
        if self._hilo_id:
            ctypes.windll.user32.PostThreadMessageW(self._hilo_id, WM_QUIT, 0, 0)

    def pulsacion_nueva(self, tecla: int, suelta: bool, ahora: float | None = None) -> bool:
        """¿Cuenta este evento como una pulsación nueva del botón? (puro, para probar)

        Una suelta nunca cuenta, pero libera la tecla. Una tecla que ya estaba
        apretada es la repetición automática: no cuenta. Y dos teclas seguidas
        (AltGr = Ctrl + Alt derecho) cuentan una, por el rebote.
        """
        if suelta:
            self._apretadas.discard(tecla)
            return False
        if tecla in self._apretadas:
            return False
        self._apretadas.add(tecla)
        return self._rebote.es_nueva(ahora)

    def _atender(self) -> None:
        # De una en una: dos aperturas a la vez dejaban el dictado abierto dos veces.
        with self._atendiendo:
            try:
                self.al_pulsar()
            except Exception:  # noqa: BLE001
                registro.exception("fallo atendiendo el botón")

    def correr(self) -> None:
        if not hay_soporte():
            return
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        HWND, HANDLE, HINSTANCE = ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        WPARAM, LPARAM = ctypes.c_size_t, ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, HWND, w.UINT, WPARAM, LPARAM)
        kernel32.GetModuleHandleW.restype = HINSTANCE
        user32.CreateWindowExW.restype = HWND
        user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, HWND, ctypes.c_void_p, HINSTANCE, ctypes.c_void_p]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [HWND, w.UINT, WPARAM, LPARAM]
        user32.GetRawInputData.argtypes = [HANDLE, w.UINT, ctypes.c_void_p, ctypes.POINTER(w.UINT), w.UINT]
        user32.GetRawInputDeviceInfoW.argtypes = [HANDLE, w.UINT, ctypes.c_void_p, ctypes.POINTER(w.UINT)]
        user32.DestroyWindow.argtypes = [HWND]
        user32.UnregisterClassW.argtypes = [w.LPCWSTR, HINSTANCE]

        class RAWINPUTDEVICE(ctypes.Structure):
            _fields_ = [("usUsagePage", w.USHORT), ("usUsage", w.USHORT), ("dwFlags", w.DWORD), ("hwndTarget", HWND)]

        class RAWINPUTHEADER(ctypes.Structure):
            _fields_ = [("dwType", w.DWORD), ("dwSize", w.DWORD), ("hDevice", HANDLE), ("wParam", WPARAM)]

        class RAWKEYBOARD(ctypes.Structure):
            _fields_ = [("MakeCode", w.USHORT), ("Flags", w.USHORT), ("Reserved", w.USHORT), ("VKey", w.USHORT), ("Message", w.UINT), ("ExtraInformation", w.ULONG)]

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", HINSTANCE), ("hIcon", HANDLE), ("hCursor", HANDLE), ("hbrBackground", HANDLE),
                        ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]

        def nombre_del_aparato(h: Any) -> str:
            with self._cerrojo:
                if h in self._nombres:
                    return self._nombres[h]
            n = w.UINT(0)
            user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(n))
            buf = ctypes.create_unicode_buffer(n.value + 1)
            user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(n))
            with self._cerrojo:
                self._nombres[h] = buf.value
            return buf.value

        def wndproc(hwnd: Any, msg: int, wp: int, lp: int) -> int:
            if msg != WM_INPUT:
                return user32.DefWindowProcW(hwnd, msg, wp, lp)
            try:
                size = w.UINT(0)
                user32.GetRawInputData(lp, RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
                buf = (ctypes.c_ubyte * max(size.value, 1))()
                user32.GetRawInputData(lp, RID_INPUT, buf, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
                hdr = RAWINPUTHEADER.from_buffer(buf)
                if hdr.dwType == RIM_TYPEKEYBOARD and self._rutas:
                    k = RAWKEYBOARD.from_buffer(buf, ctypes.sizeof(RAWINPUTHEADER))
                    if self.es_del_boton(nombre_del_aparato(hdr.hDevice)):
                        # Se atiende aparte: abrir el dictado tarda segundos y
                        # aquí no se puede esperar.
                        if self.pulsacion_nueva(int(k.VKey), bool(k.Flags & 1)):
                            threading.Thread(target=self._atender, name="minimic-boton", daemon=True).start()
            except Exception:  # noqa: BLE001 - una pulsación rara no tumba la escucha
                registro.debug("raw input", exc_info=True)
            return 0

        proc = WNDPROC(wndproc)
        clase = f"MiniMicBoton{threading.get_ident()}"
        wc = WNDCLASS()
        wc.lpfnWndProc = proc
        wc.lpszClassName = clase
        wc.hInstance = kernel32.GetModuleHandleW(None)
        if not user32.RegisterClassW(ctypes.byref(wc)):
            registro.warning("no se pudo registrar la ventana del botón: %s", ctypes.WinError())
            return
        hwnd = user32.CreateWindowExW(0, clase, "minimic-boton", 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
        if not hwnd:
            user32.UnregisterClassW(clase, wc.hInstance)
            registro.warning("no se pudo crear la ventana del botón: %s", ctypes.WinError())
            return
        aparatos = (RAWINPUTDEVICE * 1)(RAWINPUTDEVICE(1, 6, RIDEV_INPUTSINK, hwnd))
        if not user32.RegisterRawInputDevices(aparatos, 1, ctypes.sizeof(RAWINPUTDEVICE)):
            registro.warning("no se pudo apuntar a Raw Input: %s", ctypes.WinError())
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(clase, wc.hInstance)
            return
        self._hilo_id = kernel32.GetCurrentThreadId()
        self.escuchando = True
        registro.info("oyendo el botón Bluetooth por Raw Input")
        try:
            msg = w.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self.escuchando = False
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(clase, wc.hInstance)


__all__ = ["Boton", "EscuchaBoton", "Rebote", "buscar", "vigilar", "misma_interfaz", "instancia_de", "direccion_del_padre", "NOMBRE_DE_FABRICA"]
