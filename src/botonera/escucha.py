"""Escuchar lo que manda el teclado, porque no se le puede preguntar.

La Botonera no devuelve lo que tiene grabado, así que la única comprobación
posible es la que haría uno a mano: pulsar y ver qué llega. Esto lo hace por
*Raw Input* de Windows, que dice de qué aparato viene cada pulsación, y se
queda solo con las del teclado (por cable ``514C:8850``; por Bluetooth, con
el VID/PID de Apple que pone el chip). Sirve para el botón «Escuchar el
teclado» del panel y para ``python -m botonera escuchar``.

Se ejecuta en el hilo que lo llame: crea una ventana invisible, se apunta a
teclado, ratón y control de consumo con ``RIDEV_INPUTSINK`` (llegan aunque no
tenga el foco) y bombea mensajes hasta que pasa el tiempo. Solo una escucha a
la vez.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
import re
import threading
import time
from typing import Any

from sikaimini.protocolo import CONSUMO

_CERROJO = threading.Lock()

WM_INPUT, RIDEV_INPUTSINK, RIDEV_REMOVE, RID_INPUT = 0x00FF, 0x00000100, 0x00000001, 0x10000003
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD, RIM_TYPEHID = 0, 1, 2
RIDI_DEVICENAME = 0x20000007
RI_MOUSE_LEFT_DOWN, RI_MOUSE_RIGHT_DOWN, RI_MOUSE_MIDDLE_DOWN, RI_MOUSE_WHEEL = 0x0001, 0x0004, 0x0010, 0x0400

_CONSUMO_INV = {v: k for k, v in CONSUMO.items()}

#: Códigos de tecla virtual de Windows con nombre propio.
NOMBRES_VK: dict[int, str] = {
    0x08: "retroceso", 0x09: "tab", 0x0D: "intro", 0x13: "pausa", 0x14: "bloqmayus", 0x1B: "esc", 0x20: "espacio",
    0x21: "repag", 0x22: "avpag", 0x23: "fin", 0x24: "inicio", 0x25: "izquierda", 0x26: "arriba", 0x27: "derecha", 0x28: "abajo",
    0x2C: "impr", 0x2D: "insert", 0x2E: "supr", 0x5B: "win", 0x5C: "rwin", 0x5D: "menu", 0x91: "bloqdespl",
    0xA0: "mayus", 0xA1: "rmayus", 0xA2: "ctrl", 0xA3: "rctrl", 0xA4: "alt", 0xA5: "ralt",
    0x10: "mayus", 0x11: "ctrl", 0x12: "alt",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
    0xAD: "silencio", 0xAE: "vol-", 0xAF: "vol+", 0xB0: "siguiente", 0xB1: "anterior", 0xB2: "parar", 0xB3: "reproducir",
}
NOMBRES_VK.update({0x30 + i: str(i) for i in range(10)})
NOMBRES_VK.update({0x41 + i: chr(ord("a") + i) for i in range(26)})
NOMBRES_VK.update({0x70 + i: f"f{i + 1}" for i in range(24)})
MODIFICADORES_VK = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
_ORDEN_MODS = ("ctrl", "mayus", "alt", "win", "rctrl", "rmayus", "ralt", "rwin")


def nombre_de_vk(vk: int) -> str:
    return NOMBRES_VK.get(vk, f"vk{vk:#04x}")


def origen_de(nombre_del_aparato: str) -> str:
    """«cable», «bluetooth» u «otro», según el VID/PID que lleva la ruta del aparato."""
    m = re.search(r"VID[_&](?:0[12])?([0-9A-F]{4})[_&]PID[_&](?:0)?([0-9A-F]{4})", nombre_del_aparato, re.I)
    if not m:
        return "otro"
    vid, pid = m.group(1).upper(), m.group(2).upper()
    if (vid, pid) == ("514C", "8850"):
        return "cable"
    if (vid, pid) == ("05AC", "022C"):
        return "bluetooth"
    return "otro"


def _decodificar_consumo(datos: bytes) -> str:
    """El informe de control de consumo: identificador y un uso de 16 bits, bajo primero."""
    if len(datos) >= 3:
        uso = datos[1] | (datos[2] << 8)
        if uso:
            return _CONSUMO_INV.get(uso, f"consumo {uso:#06x}")
    return ""


def hay_soporte() -> bool:
    return os.name == "nt"


def capturar(segundos: float = 10.0, solo_el_teclado: bool = True) -> list[dict[str, Any]]:
    """Escucha ``segundos`` y devuelve las pulsaciones: [{t, origen, tecla, aparato}].

    Junta los modificadores con la tecla que sigue (``ctrl-mayus-f13``); un
    modificador solo, sin tecla detrás, se apunta al soltarlo. La rueda y los
    botones del ratón salen como ``rueda-arriba``, ``clic``…
    """
    if not hay_soporte():
        raise RuntimeError("la escucha de pulsaciones es cosa de Windows")
    if not _CERROJO.acquire(blocking=False):
        raise RuntimeError("ya hay una escucha en marcha")
    try:
        return _capturar(segundos, solo_el_teclado)
    finally:
        _CERROJO.release()


def _capturar(segundos: float, solo_el_teclado: bool) -> list[dict[str, Any]]:
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

    class RAWMOUSE(ctypes.Structure):
        _fields_ = [("usFlags", w.USHORT), ("usButtonFlags", w.USHORT), ("usButtonData", w.USHORT), ("ulRawButtons", w.ULONG),
                    ("lLastX", ctypes.c_long), ("lLastY", ctypes.c_long), ("ulExtraInformation", w.ULONG)]

    class RAWHID(ctypes.Structure):
        _fields_ = [("dwSizeHid", w.DWORD), ("dwCount", w.DWORD)]

    class WNDCLASS(ctypes.Structure):
        _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", HINSTANCE), ("hIcon", HANDLE), ("hCursor", HANDLE), ("hbrBackground", HANDLE),
                    ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]

    nombres: dict[Any, str] = {}

    def nombre_del_aparato(h: Any) -> str:
        if h in nombres:
            return nombres[h]
        n = w.UINT(0)
        user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(n))
        buf = ctypes.create_unicode_buffer(n.value + 1)
        user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(n))
        nombres[h] = buf.value
        return buf.value

    t0 = time.time()
    salida: list[dict[str, Any]] = []
    pulsados: list[str] = []  # modificadores en el aire
    hubo_tecla_con_mods = False

    def apuntar(origen: str, tecla: str, aparato: str) -> None:
        salida.append({"t": round(time.time() - t0, 2), "origen": origen, "tecla": tecla, "aparato": aparato})

    def tratar(hdr: Any, buf: Any, off: int) -> None:
        nonlocal hubo_tecla_con_mods
        aparato = nombre_del_aparato(hdr.hDevice)
        origen = origen_de(aparato)
        if solo_el_teclado and origen == "otro":
            return
        if hdr.dwType == RIM_TYPEKEYBOARD:
            k = RAWKEYBOARD.from_buffer(buf, off)
            suelta = bool(k.Flags & 1)
            nombre = nombre_de_vk(k.VKey)
            if k.VKey in MODIFICADORES_VK:
                if not suelta:
                    if nombre not in pulsados:
                        pulsados.append(nombre)
                        hubo_tecla_con_mods = False
                else:
                    if nombre in pulsados:
                        pulsados.remove(nombre)
                    if not pulsados and not hubo_tecla_con_mods:
                        apuntar(origen, nombre, aparato)  # modificador solo
                    hubo_tecla_con_mods = bool(pulsados) and hubo_tecla_con_mods
                return
            if suelta:
                return
            mods = sorted(set(pulsados), key=lambda m: _ORDEN_MODS.index(m) if m in _ORDEN_MODS else 99)
            hubo_tecla_con_mods = bool(mods)
            apuntar(origen, "-".join(mods + [nombre]), aparato)
        elif hdr.dwType == RIM_TYPEMOUSE:
            m = RAWMOUSE.from_buffer(buf, off)
            f = m.usButtonFlags
            if f & RI_MOUSE_WHEEL:
                delta = ctypes.c_short(m.usButtonData).value
                apuntar(origen, "rueda-arriba" if delta > 0 else "rueda-abajo", aparato)
            if f & RI_MOUSE_LEFT_DOWN:
                apuntar(origen, "clic", aparato)
            if f & RI_MOUSE_RIGHT_DOWN:
                apuntar(origen, "clic-derecho", aparato)
            if f & RI_MOUSE_MIDDLE_DOWN:
                apuntar(origen, "clic-central", aparato)
        elif hdr.dwType == RIM_TYPEHID:
            hh = RAWHID.from_buffer(buf, off)
            inicio = off + ctypes.sizeof(RAWHID)
            datos = bytes(buf[inicio:inicio + hh.dwSizeHid * hh.dwCount])
            nombre = _decodificar_consumo(datos)
            if nombre:
                apuntar(origen, nombre, aparato)

    def wndproc(hwnd: Any, msg: int, wp: int, lp: int) -> int:
        if msg == WM_INPUT:
            size = w.UINT(0)
            user32.GetRawInputData(lp, RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            buf = (ctypes.c_ubyte * max(size.value, 1))()
            user32.GetRawInputData(lp, RID_INPUT, buf, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            hdr = RAWINPUTHEADER.from_buffer(buf)
            try:
                tratar(hdr, buf, ctypes.sizeof(RAWINPUTHEADER))
            except Exception:  # noqa: BLE001 - una pulsación rara no tumba la escucha
                pass
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    proc = WNDPROC(wndproc)
    clase = f"BotoneraEscucha{threading.get_ident()}"
    wc = WNDCLASS()
    wc.lpfnWndProc = proc
    wc.lpszClassName = clase
    wc.hInstance = kernel32.GetModuleHandleW(None)
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise ctypes.WinError()
    hwnd = user32.CreateWindowExW(0, clase, "botonera-escucha", 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
    if not hwnd:
        user32.UnregisterClassW(clase, wc.hInstance)
        raise ctypes.WinError()
    dispositivos = (RAWINPUTDEVICE * 3)(
        RAWINPUTDEVICE(1, 6, RIDEV_INPUTSINK, hwnd),     # teclado
        RAWINPUTDEVICE(1, 2, RIDEV_INPUTSINK, hwnd),     # ratón
        RAWINPUTDEVICE(0x0C, 1, RIDEV_INPUTSINK, hwnd),  # control de consumo
    )
    try:
        if not user32.RegisterRawInputDevices(dispositivos, 3, ctypes.sizeof(RAWINPUTDEVICE)):
            raise ctypes.WinError()
        msg = w.MSG()
        while time.time() - t0 < segundos:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)
    finally:
        quitar = (RAWINPUTDEVICE * 3)(
            RAWINPUTDEVICE(1, 6, RIDEV_REMOVE, None), RAWINPUTDEVICE(1, 2, RIDEV_REMOVE, None), RAWINPUTDEVICE(0x0C, 1, RIDEV_REMOVE, None),
        )
        user32.RegisterRawInputDevices(quitar, 3, ctypes.sizeof(RAWINPUTDEVICE))
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(clase, wc.hInstance)
    return salida
