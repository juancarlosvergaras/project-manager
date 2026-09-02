"""Sonda del teclado de voz Jieli (VID 514C, PID 8850): exploración, sin aplicación todavía.

Uso:
  python sonda.py enumerar                 # interfaces HID de los dos dispositivos Jieli
  python sonda.py luz azul|rojo|verde|off  # luz fija en las tres capas (formato del PR 175 de ch57x-keyboard-tool)
  python sonda.py tecla N capa COMBO       # asigna la tecla N (1..) en la capa (1..3): 'ctrl-a', 'enter', 'win-h', 'f13'
  python sonda.py crudo HEX                # manda un paquete a mano y enseña el acuse

El firmware NO devuelve la configuración (los comandos FA/FB de otros modelos contestan
con el acuse genérico 03 07 …), así que la única verificación es pulsar la tecla y
capturar lo que llega con captura_teclas.py.
"""
import sys, hid

VID, PID = 0x514C, 0x8850
MODIF = {"ctrl": 0xF1, "shift": 0xF2, "alt": 0xF3, "win": 0xF4, "rctrl": 0xF5, "rshift": 0xF6, "ralt": 0xF7, "rwin": 0xF8}
TECLAS = {**{chr(c): 0x04 + c - ord("a") for c in range(ord("a"), ord("z") + 1)},
          **{str(n): 0x1E + n - 1 for n in range(1, 10)}, "0": 0x27,
          "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C, "delete": 0x4C,
          **{f"f{n}": 0x3A + n - 1 for n in range(1, 13)}, **{f"f{n}": 0x68 + n - 13 for n in range(13, 25)}}
COLORES = {"azul": (0, 0, 255), "rojo": (255, 0, 0), "verde": (0, 255, 0), "blanco": (255, 255, 255), "off": (0, 0, 0)}


def abrir():
    ruta = next(d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == 0xFF00)
    h = hid.device(); h.open_path(ruta); return h


def mandar(h, carga):
    carga = bytes(carga)[:64]
    h.write(carga + bytes(64 - len(carga)))
    r = h.read(64, timeout_ms=800)
    print(f"  > {carga[:12].hex(' ')}…   acuse: {bytes(r)[:12].hex(' ') if r else 'ninguno'}")


def luz(nombre):
    r, g, b = COLORES[nombre]; modo = 0 if nombre == "off" else 1
    h = abrir()
    for capa in (0, 1, 2):
        mandar(h, [0x03, 0xFE, 0xB0, capa, modo, r, g, b] + [r, g, b] * 16)


def tecla(n, capa, combo):
    partes = combo.lower().split("-")
    grupos = [[0, 0, MODIF[p]] for p in partes[:-1]] + [[0, 0, TECLAS[partes[-1]]]]
    h = abrir()
    mandar(h, [0x03, 0xFD, n, capa, 0x01, 0x00, len(grupos)] + sum(grupos, []))
    mandar(h, [0x03, 0xFD, 0xFE, 0xFF])


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "enumerar"
    if orden == "enumerar":
        for d in hid.enumerate():
            if d["vendor_id"] in (0x4C4A, VID):
                print(f"{d['vendor_id']:04X}:{d['product_id']:04X} MI{d['interface_number']} pagina={d['usage_page']:#06x} uso={d['usage']}")
    elif orden == "luz":
        luz(sys.argv[2])
    elif orden == "tecla":
        tecla(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    elif orden == "crudo":
        mandar(abrir(), bytes.fromhex(sys.argv[2]))
