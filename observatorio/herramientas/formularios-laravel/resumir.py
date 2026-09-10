"""Imprime una definición JSON de cuestionario en una línea por bloque, para revisarla."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(sys.argv[1], encoding="utf-8"))
print("TITULO:", d["titulo"])
print("INTRO:", len(d["intro"]), "párrafos | POLITICAS:", d["politicas"]["mostrar"], len(d["politicas"]["textos"]), "|", d["politicas"]["etiqueta"][:60])
print("BARRA:", d["progreso"]["barra"], "| BOTON:", d["cierre"]["boton"])


def linea(b, sangria=""):
    t = b["tipo"]
    if t == "seccion":
        print(f"{sangria}## [{b.get('numero')}] {b['titulo']}")
    elif t == "leyenda":
        print(f"{sangria}   (leyenda) {b['titulo']}: " + " | ".join(f"{i['etiqueta']}={i['texto']}" for i in b["items"]))
    elif t == "texto":
        print(f"{sangria}   (texto) {b['texto'][:90]}")
    elif t == "condicional":
        print(f"{sangria}   (condicional {b['condicion']})")
        for x in b["bloques"]:
            linea(x, sangria + "      ")
    else:
        extra = []
        for k in ("formato", "ancho", "min", "max", "extremos", "otro", "en_linea", "depende_de", "opcional_de", "placeholder"):
            if k in b:
                extra.append(f"{k}={b[k]}")
        if "opciones" in b:
            extra.append(f"opciones({len(b['opciones'])})=" + " / ".join(str(o)[:28] for o in b["opciones"]))
        if "niveles" in b:
            extra.append("niveles=" + " / ".join(x["texto"] for x in b["niveles"]))
        if "items" in b:
            extra.append("items=" + " / ".join(x["texto"] for x in b["items"]))
        print(f"{sangria}   {b.get('numero', '-')}. [{t}] {b.get('nombre')} {'*' if b.get('requerido') else ''} «{b.get('etiqueta', '')[:70]}» {' '.join(extra)}" + (f" AYUDA={b['ayuda'][:50]}" if b.get("ayuda") else ""))


for i, p in enumerate(d["pasos"]):
    print(f"\n=== PASO {i + 1}: {p['etiqueta']}")
    for b in p["bloques"]:
        linea(b)
