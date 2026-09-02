# Captura de entrada cruda (Raw Input) durante N segundos: teclado y control de consumo,
# con el dispositivo de origen de cada pulsación.
import ctypes, ctypes.wintypes as w, sys, time
user32 = ctypes.windll.user32; kernel32 = ctypes.windll.kernel32
kernel32.GetModuleHandleW.restype = w.HMODULE
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.DefWindowProcW.restype = ctypes.c_long
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.GetRawInputData.argtypes = [w.HANDLE, w.UINT, w.LPVOID, ctypes.POINTER(w.UINT), w.UINT]
user32.GetRawInputDeviceInfoW.argtypes = [w.HANDLE, w.UINT, w.LPVOID, ctypes.POINTER(w.UINT)]

DURACION = float(sys.argv[1]) if len(sys.argv) > 1 else 150
WM_INPUT, WM_DESTROY, RIDEV_INPUTSINK, RID_INPUT = 0x00FF, 0x0002, 0x00000100, 0x10000003
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD, RIM_TYPEHID = 0, 1, 2
RIDI_DEVICENAME = 0x20000007
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
w.HMODULE = ctypes.c_void_p; w.HINSTANCE = ctypes.c_void_p; w.HWND = ctypes.c_void_p; w.HMENU = ctypes.c_void_p; w.HANDLE = ctypes.c_void_p; w.WPARAM = ctypes.c_size_t; w.LPARAM = ctypes.c_ssize_t
class RAWINPUTDEVICE(ctypes.Structure): _fields_ = [("usUsagePage", w.USHORT), ("usUsage", w.USHORT), ("dwFlags", w.DWORD), ("hwndTarget", w.HWND)]
class RAWINPUTHEADER(ctypes.Structure): _fields_ = [("dwType", w.DWORD), ("dwSize", w.DWORD), ("hDevice", w.HANDLE), ("wParam", w.WPARAM)]
class RAWKEYBOARD(ctypes.Structure): _fields_ = [("MakeCode", w.USHORT), ("Flags", w.USHORT), ("Reserved", w.USHORT), ("VKey", w.USHORT), ("Message", w.UINT), ("ExtraInformation", w.ULONG)]
class RAWHID(ctypes.Structure): _fields_ = [("dwSizeHid", w.DWORD), ("dwCount", w.DWORD), ("bRawData", ctypes.c_ubyte * 1)]
class WNDCLASS(ctypes.Structure): _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HANDLE), ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE), ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]
nombres = {}
def nombre(h):
    if h in nombres: return nombres[h]
    n = w.UINT(0); user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(n))
    buf = ctypes.create_unicode_buffer(n.value + 1); user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(n))
    s = buf.value
    import re
    m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})(?:&MI_(\d\d))?(?:&Col(\d\d))?", s, re.I)
    nombres[h] = f"{m.group(1)}:{m.group(2)} MI{m.group(3) or '?'} Col{m.group(4) or '?'}" if m else s[-40:]
    return nombres[h]
t0 = time.time()
def wndproc(hwnd, msg, wp, lp):
    if msg == WM_INPUT:
        size = w.UINT(0)
        user32.GetRawInputData(lp, RID_INPUT, None, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        buf = (ctypes.c_ubyte * size.value)()
        user32.GetRawInputData(lp, RID_INPUT, buf, ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        hdr = RAWINPUTHEADER.from_buffer(buf); off = ctypes.sizeof(RAWINPUTHEADER)
        t = f"{time.time()-t0:6.2f}s"
        if hdr.dwType == RIM_TYPEKEYBOARD:
            k = RAWKEYBOARD.from_buffer(buf, off)
            print(f"{t} TECLADO {nombre(hdr.hDevice):28} vk=0x{k.VKey:02X} scan=0x{k.MakeCode:02X} {'suelta' if k.Flags & 1 else 'PULSA '} flags={k.Flags}", flush=True)
        elif hdr.dwType == RIM_TYPEHID:
            hh = RAWHID.from_buffer(buf, off); datos = bytes(buf[off+8 : off+8+hh.dwSizeHid*hh.dwCount])
            print(f"{t} HID     {nombre(hdr.hDevice):28} datos={datos.hex(' ')}", flush=True)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)
proc = WNDPROC(wndproc)
wc = WNDCLASS(); wc.lpfnWndProc = proc; wc.lpszClassName = "CapturaRawInput"; wc.hInstance = kernel32.GetModuleHandleW(None)
user32.RegisterClassW(ctypes.byref(wc))
hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "captura", 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
devs = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(1, 6, RIDEV_INPUTSINK, hwnd), RAWINPUTDEVICE(0x0C, 1, RIDEV_INPUTSINK, hwnd))
assert user32.RegisterRawInputDevices(devs, 2, ctypes.sizeof(RAWINPUTDEVICE)), ctypes.WinError()
print(f"capturando {DURACION:.0f} s...", flush=True)
msg = w.MSG()
while time.time() - t0 < DURACION:
    while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))
    time.sleep(0.01)
print("fin de la captura", flush=True)
