"""Protocolo del LQ_Keyboard (teclado de voz Jieli 514C:8850), sacado con Frida el 1/9/2026.

Paquete: 03 <orden> <capa> <arg> <len> <carga…> … <XOR de bytes 1..62 en el byte 63>
Acuse:   03 06 … (03 07 = rechazo).  Órdenes: 0c info, 04 leer capa (arg ff = todas las
teclas; contesta 03 03 <capa> <tecla> <len> <registro>), 01 escribir tecla, 0d/0e leer y
escribir ajustes (modo micrófono), 0a leer luces.
Registro de tecla: [flags][6×00][n][00][…]: flags 00 → [código]; flags 04 → [mods][nteclas][códigos…].
"""
import hid

VID, PID = 0x514C, 0x8850
MODS = {0x01: "ctrl", 0x02: "shift", 0x04: "alt", 0x08: "win", 0x10: "rctrl", 0x20: "rshift", 0x40: "ralt", 0x80: "rwin"}
NOMBRES = {0x04 + i: chr(97 + i) for i in range(26)}
NOMBRES.update({0x1E + i: str(i + 1) for i in range(9)}); NOMBRES[0x27] = "0"
NOMBRES.update({0x28: "enter", 0x29: "esc", 0x2A: "backspace", 0x2B: "tab", 0x2C: "space", 0x4C: "delete"})
NOMBRES.update({0x3A + i: f"f{i+1}" for i in range(12)}); NOMBRES.update({0x68 + i: f"f{i+13}" for i in range(12)})
CODIGOS = {v: k for k, v in NOMBRES.items()}
MODS_INV = {v: k for k, v in MODS.items()}


def paquete(orden, capa=0, arg=0, carga=b""):
    p = bytearray(64); p[0] = 3; p[1] = orden; p[2] = capa; p[3] = arg; p[4] = len(carga); p[5:5 + len(carga)] = carga
    x = 0
    for b in p[1:63]: x ^= b
    p[63] = x
    return bytes(p)


def abrir():
    ruta = next(d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == 0xFF00)
    h = hid.device(); h.open_path(ruta); return h


def intercambio(h, p, espera_ms=500):
    h.write(p); salida = []
    while True:
        r = h.read(64, timeout_ms=espera_ms)
        if not r: break
        r = bytes(r); salida.append(r)
        if r[1] in (0x06, 0x07): break   # acuse final
        espera_ms = 200
    return salida


def describe(reg):
    if len(reg) < 9: return f"vacío ({reg.hex(' ')})"
    flags, n, cuerpo = reg[0], reg[7], reg[9:]
    if flags == 0x00:
        return NOMBRES.get(cuerpo[0], f"<{cuerpo[0]:#x}>") if cuerpo else "nada"
    if flags == 0x04:
        mods = [v for k, v in MODS.items() if cuerpo[0] & k]
        teclas = [NOMBRES.get(c, f"<{c:#x}>") for c in cuerpo[2:2 + cuerpo[1]]]
        return "-".join(mods + teclas) if (mods or teclas) else "nada"
    return f"tipo {flags:#x}: {reg.hex(' ')}"


def registro(combo):
    partes = combo.lower().split("-")
    mods = 0
    for m in partes[:-1]: mods |= MODS_INV[m]
    teclas = [] if partes[-1] in ("", "nada") else [CODIGOS[partes[-1]]]
    if mods == 0 and len(teclas) == 1:
        return bytes([0x00] + [0] * 6 + [0x01, 0x00, teclas[0]])
    cuerpo = bytes([mods, len(teclas)] + teclas)
    return bytes([0x04] + [0] * 6 + [len(cuerpo), 0x00]) + cuerpo


def leer(h, capa=0):
    print("info:", intercambio(h, paquete(0x0C))[0][5:13].hex(" "))
    aj = intercambio(h, paquete(0x0D, 0, 1, b"\x01"))[0]
    print("ajustes:", aj[5:5 + aj[4]].hex(" "), "(último byte = modo micrófono: 00 mantener, 01 pulsar)")
    for r in intercambio(h, paquete(0x04, capa, 0xFF)):
        if r[1] == 0x03: print(f"  capa {r[2]+1} tecla {r[3]+1}: {describe(r[5:5 + r[4]])}")


def escribir(h, tecla, combo, capa=0):
    r = intercambio(h, paquete(0x01, capa, tecla - 1, registro(combo)))
    print(f"tecla {tecla} := {combo}: {'OK' if r and r[-1][1] == 0x06 else 'RECHAZADO ' + (r[-1].hex(' ') if r else 'sin respuesta')}")


def modo_microfono(h, modo):
    """0 = mantener pulsado para captar; 1 = pulsar para empezar y pulsar para parar."""
    r = intercambio(h, paquete(0x0E, 0, 1, bytes([1, 1, modo])))
    print(f"modo micrófono := {modo}: {'OK' if r and r[-1][1] == 0x06 else 'RECHAZADO'}")


if __name__ == "__main__":
    import sys
    h = abrir(); orden = sys.argv[1] if len(sys.argv) > 1 else "leer"
    if orden == "leer": leer(h, int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0)
    elif orden == "tecla": escribir(h, int(sys.argv[2]), sys.argv[3], int(sys.argv[4]) - 1 if len(sys.argv) > 4 else 0)
    elif orden == "mic": modo_microfono(h, int(sys.argv[2]))
    h.close()
