"""Espía de hidapi dentro de LQ_Keyboard.exe: registra cada hid_write / hid_read.

Uso: arranca LQ_Keyboard.exe tú mismo y luego  python exploracion_jieli/espia_hidapi.py
Escribe en exploracion_jieli/espia.log y en pantalla. Ctrl+C para terminar.
"""
import sys, time, frida

CODIGO = r"""
var mod = "hidapi.dll";
function hex(p, n) { try { return Array.from(new Uint8Array(p.readByteArray(n))).map(b => ("0" + b.toString(16)).slice(-2)).join(" "); } catch (e) { return "?"; } }
function hook(nombre, onEnter, onLeave) {
    var m = Process.getModuleByName(mod); var d = m.findExportByName ? m.findExportByName(nombre) : Module.findExportByName(mod, nombre);
    if (!d) { send({ev: "aviso", msg: "sin export " + nombre}); return; }
    Interceptor.attach(d, { onEnter: onEnter, onLeave: onLeave });
}
hook("hid_open_path", function (a) { this.p = a[0].readCString(); }, function (r) { send({ev: "open", path: this.p, h: r.toString()}); });
hook("hid_write", function (a) { this.h = a[0].toString(); this.buf = a[1]; this.n = a[2].toInt32(); },
     function (r) { send({ev: "write", h: this.h, n: this.n, ret: r.toInt32(), datos: hex(this.buf, Math.min(this.n, 80))}); });
function leer(nombre) {
    hook(nombre, function (a) { this.h = a[0].toString(); this.buf = a[1]; this.n = a[2].toInt32(); this.t = nombre === "hid_read_timeout" ? a[3].toInt32() : -1; },
         function (r) { var k = r.toInt32(); if (k > 0) send({ev: "read", fn: nombre, h: this.h, n: k, datos: hex(this.buf, Math.min(k, 80))}); else if (k < 0) send({ev: "read", fn: nombre, h: this.h, n: k}); });
}
leer("hid_read"); leer("hid_read_timeout");
hook("hid_close", function (a) { this.h = a[0].toString(); }, function (r) { send({ev: "close", h: this.h}); });
send({ev: "listo"});
"""

def main():
    log = open("exploracion_jieli/espia.log", "a", encoding="utf-8")
    t0 = time.time()
    def anota(linea):
        s = f"{time.time()-t0:8.3f}s {linea}"; print(s, flush=True); log.write(s + "\n"); log.flush()
    sesion = frida.attach("LQ_Keyboard.exe")
    script = sesion.create_script(CODIGO)
    def on_message(m, _):
        if m["type"] != "send": anota(f"?? {m}"); return
        p = m["payload"]; ev = p["ev"]
        if ev == "write": anota(f"ESCRIBE n={p['n']} ret={p['ret']}  {p['datos']}")
        elif ev == "read": anota(f"LEE    {p['fn']} n={p['n']}  {p.get('datos','')}")
        elif ev == "open": anota(f"ABRE   {p['path']} -> {p['h']}")
        elif ev == "close": anota(f"CIERRA {p['h']}")
        else: anota(str(p))
    script.on("message", on_message)
    script.load()
    anota("enganchado a LQ_Keyboard.exe; usa el programa (leer, asignar una tecla, guardar, cambiar modo de micrófono). Ctrl+C para salir.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
    sesion.detach()

if __name__ == "__main__":
    main()
