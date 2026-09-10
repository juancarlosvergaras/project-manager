"""Convierte los tres formularios Laravel de unicartagena.edu.co a definiciones JSON del módulo de cuestionarios.

Uso: python convertir.py <archivo.html> <clave> > salida.json
"""
import sys, re, json
from extraer import Parser, Nodo

sys.stdout.reconfigure(encoding="utf-8")


def limpiar(t):
    return re.sub(r"\s+", " ", t or "").strip()


def es(n, tag=None, clase=None):
    if not isinstance(n, Nodo):
        return False
    if tag and n.tag != tag:
        return False
    if clase and clase not in n.clases():
        return False
    return True


def etiqueta_y_numero(texto):
    """'12. ¿Cuáles…? *' -> (numero, etiqueta, requerido)."""
    t = limpiar(texto)
    req = t.endswith("*") or t.endswith("(*)")
    t = re.sub(r"\s*\(?\*\)?$", "", t).strip()
    m = re.match(r"^(\d+)\.\s+(.*)$", t)
    if m:
        return int(m.group(1)), m.group(2), req
    return None, t, req


def texto_md(n):
    """Texto de un nodo conservando negritas (**x**) y saltos de línea (<br>)."""
    partes = []
    for h in n.hijos:
        if isinstance(h, str):
            partes.append(re.sub(r"\s+", " ", h))
        elif h.tag == "strong":
            partes.append("**" + limpiar(h.texto()) + "**")
        elif h.tag == "br":
            partes.append("\n")
        else:
            partes.append(re.sub(r"\s+", " ", h.texto()))
    t = "".join(partes)
    lineas = [x.strip() for x in t.split("\n")]
    return "\n".join(x for x in lineas if x).strip()


def opciones_de_select(sel):
    ops = []
    for o in sel.buscar(lambda x: x.tag == "option"):
        v = o.attrs.get("value")
        txt = limpiar(o.texto())
        if v == "" or (v is None and re.match(r"^(Seleccione|--)", txt)):
            continue
        ops.append(txt if v is None or v == txt else {"valor": v, "texto": txt})
    return ops


def aplanar(n, ancho=None):
    """Devuelve los hijos 'semánticos' de un nodo, desenvolviendo filas y columnas de Bootstrap.
    Cada elemento es (nodo, ancho_de_columna)."""
    salida = []
    for h in n.hijos:
        if not isinstance(h, Nodo):
            continue
        cl = h.clases()
        semanticas = {"section-header", "legend-card", "conditional-block", "likert-row", "checkbox-group",
                      "rubrica-escala", "form-check", "step-nav", "steps-progress", "steps-progress-meta", "list-group"}
        if h.tag == "div" and not (set(cl) & semanticas) and not any(c.startswith("align-items") for c in cl):
            a = ancho
            for c in cl:
                m = re.match(r"col-md-(\d+)", c)
                if m:
                    a = int(m.group(1))
            salida.extend(aplanar(h, a))
        else:
            salida.append((h, ancho))
    return salida


def convertir(html, clave):
    p = Parser()
    p.feed(html)
    raiz = p.raiz
    caja = raiz.buscar(lambda x: "contenido-formulario-inscripcion" in x.clases())[0]
    form = raiz.buscar(lambda x: x.tag == "form")[0]

    # ---- cabecera: título, introducción y políticas
    titulo = limpiar(caja.buscar(lambda x: "contenido-formulario-title" in x.clases())[0].texto())
    intro, politicas_textos, etiqueta_acepta = [], [], None
    en_politicas, titulo_politicas = False, None
    for h in caja.hijos:
        if not isinstance(h, Nodo):
            continue
        if h.tag == "strong":
            en_politicas = True
            titulo_politicas = limpiar(h.texto())
        elif h.tag == "p":
            (politicas_textos if en_politicas else intro).append(texto_md(h))
        elif "form-check" in h.clases():
            lab = h.buscar(lambda x: x.tag == "label")
            if lab:
                etiqueta_acepta = limpiar(lab[0].texto())
    politicas = {"mostrar": bool(politicas_textos), "titulo": titulo_politicas or "Términos y Política de Tratamiento de Datos",
                 "textos": politicas_textos, "etiqueta": etiqueta_acepta or "Autorizo el tratamiento de mis datos personales conforme a lo descrito"}

    # ---- pasos
    etiquetas = [limpiar(x.texto()).lstrip("· ").strip() for x in form.buscar(lambda x: "step-label" in x.clases())]
    barra = bool(form.buscar(lambda x: "steps-progress-meta" in x.clases()))
    pasos = []
    boton_enviar = None
    for i, paso in enumerate(form.buscar(lambda x: "form-step" in x.clases())):
        bloques = convertir_bloques(aplanar(paso))
        titulo_paso = None
        if bloques and bloques[0]["tipo"] == "seccion":
            titulo_paso = bloques[0]["titulo"]
        for b in form.buscar(lambda x: x.tag == "button" and x.attrs.get("type") == "submit"):
            boton_enviar = limpiar(b.texto())
        pasos.append({"etiqueta": etiquetas[i] if i < len(etiquetas) else f"Paso {i + 1}", "bloques": bloques})

    return {
        "titulo": titulo,
        "intro": intro,
        "politicas": politicas,
        "progreso": {"barra": barra},
        "pasos": pasos,
        "cierre": {"boton": boton_enviar or "Enviar respuestas", "titulo": "¡Gracias por su respuesta!",
                   "mensaje": "Sus respuestas fueron registradas correctamente."},
    }


ICONOS = {"fa-id-card": "🪪", "fa-brain": "🧠", "fa-laptop-code": "💻", "fa-chart-line": "📈", "fa-triangle-exclamation": "⚠️",
          "fa-landmark-flag": "🏛️", "fa-landmark": "🏛️", "fa-user": "👤", "fa-clipboard-check": "📋", "fa-database": "🗄️",
          "fa-shield-alt": "🛡️", "fa-users-cog": "👥", "fa-bullseye": "🎯", "fa-server": "🖥️", "fa-robot": "🤖",
          "fa-shield-halved": "🛡️", "fa-scale-balanced": "⚖️", "fa-user-shield": "🔐", "fa-lightbulb": "💡"}

CONDICIONES = {
    "bloque-18-19": {"campo": "frecuencia_uso_laboral", "operador": "!=", "valor": "Nunca"},
    "bloque-25": {"campo": "experiencia_problema_ia", "operador": "!=", "valor": "No"},
}


def convertir_bloques(items):
    bloques = []
    i = 0
    pendiente_label = None  # (numero, etiqueta, requerido, for)
    pendiente_ayuda = []
    ancho_label = None

    def campo_base(tipo, nombre, numero, etiqueta, requerido, ancho):
        c = {"tipo": tipo, "nombre": nombre, "etiqueta": etiqueta}
        if numero is not None:
            c["numero"] = numero
        if requerido:
            c["requerido"] = True
        if ancho and ancho != 12:
            c["ancho"] = ancho
        return c

    while i < len(items):
        n, ancho = items[i]
        cl = n.clases()
        i += 1
        if n.tag == "div" and "section-header" in cl:
            badge = n.buscar(lambda x: "section-badge" in x.clases())
            ico = n.buscar(lambda x: x.tag == "i")
            sec = {"tipo": "seccion", "numero": limpiar(badge[0].texto()) if badge else None,
                   "titulo": limpiar(n.buscar(lambda x: "section-title" in x.clases())[0].texto())}
            if ico:
                fa = next((c for c in ico[0].clases() if c.startswith("fa-")), None)
                if fa in ICONOS:
                    sec["icono"] = ICONOS[fa]
            bloques.append(sec)
            continue
        if n.tag == "div" and "legend-card" in cl:
            items_ley = []
            for it in n.buscar(lambda x: "legend-item" in x.clases()):
                nivel = next((c.split("--n")[1] for c in it.clases() if "--n" in c), None)
                items_ley.append({"nivel": int(nivel) if nivel else None,
                                  "etiqueta": limpiar(it.buscar(lambda x: "legend-badge" in x.clases())[0].texto()),
                                  "texto": limpiar(it.buscar(lambda x: "legend-text" in x.clases())[0].texto())})
            t = n.buscar(lambda x: "legend-title" in x.clases())
            d = n.buscar(lambda x: "legend-desc" in x.clases())
            bloques.append({"tipo": "leyenda", "titulo": limpiar(t[0].texto()) if t else "", "descripcion": limpiar(d[0].texto()) if d else "", "items": items_ley})
            continue
        if n.tag == "div" and "conditional-block" in cl:
            bloques.append({"tipo": "condicional", "condicion": CONDICIONES.get(n.attrs.get("id"), {}), "bloques": convertir_bloques(aplanar(n))})
            continue
        if n.tag == "div" and "step-nav" in cl:
            continue
        if n.tag == "div" and "list-group" in cl:  # sugerencias de entidad
            if bloques and bloques[-1].get("tipo") == "texto_corto":
                bloques[-1]["tipo"] = "entidad"
            continue
        if n.tag == "p":
            txt = limpiar(n.texto())
            bloques.append({"tipo": "texto", "texto": txt})
            continue
        if n.tag == "small":
            txt = limpiar(n.texto())
            if re.match(r"^Selecciona máximo", txt):
                continue
            if pendiente_label:
                pendiente_ayuda.append(txt)
            elif bloques:
                bloques[-1].setdefault("ayuda", "")
                bloques[-1]["ayuda"] = (bloques[-1]["ayuda"] + " " + txt).strip()
            continue
        if n.tag == "label":
            numero, etiqueta, req = etiqueta_y_numero(n.texto())
            if etiqueta == "Especifique" or etiqueta.startswith("Adjuntar archivo"):
                # etiqueta auxiliar: 'Especifique' pertenece al campo otro del bloque anterior; 'Adjuntar' es un archivo
                if etiqueta == "Especifique":
                    continue
            pendiente_label = (numero, etiqueta, req, n.attrs.get("for"))
            pendiente_ayuda = []
            ancho_label = ancho
            continue
        if n.tag == "div" and "likert-row" in cl:
            lab = n.buscar(lambda x: x.tag == "label" and "form-check-label" not in x.clases())[0]
            numero, etiqueta, req = etiqueta_y_numero(lab.texto())
            radios = n.buscar(lambda x: x.tag == "input" and x.attrs.get("type") == "radio")
            vals = [int(r.attrs.get("value")) for r in radios]
            caps = [limpiar(s.texto()) for s in n.buscar(lambda x: x.tag == "span" and x.padre is not None and "likert-caption" in x.padre.clases())]
            c = campo_base("escala", radios[0].attrs.get("name"), numero, etiqueta, req, None)
            c["min"], c["max"] = min(vals), max(vals)
            if caps:
                c["extremos"] = caps
            bloques.append(c)
            continue
        # ---- controles que responden a la etiqueta pendiente
        if n.tag in ("input", "select", "textarea") or (n.tag == "div" and (set(cl) & {"checkbox-group", "rubrica-escala", "form-check"})) or any(c.startswith("align-items") for c in cl):
            if n.tag == "input" and n.attrs.get("type") == "hidden":
                continue
            # campo 'otro' que acompaña al control anterior
            if n.tag == "input" and n.attrs.get("type") == "text" and (n.attrs.get("data-otros-campo") or (n.attrs.get("name", "").endswith("_otro") and not pendiente_label)):
                if bloques:
                    bloques[-1]["otro"] = {"valor": n.attrs.get("data-otros-valor") or "Otros", "etiqueta": n.attrs.get("placeholder") or "Especifique"}
                continue
            if n.tag == "input" and n.attrs.get("type") == "text" and pendiente_label and pendiente_label[3] and pendiente_label[3] != n.attrs.get("id") and n.attrs.get("name", "").endswith("_otro"):
                if bloques:
                    bloques[-1]["otro"] = {"valor": "Otros", "etiqueta": n.attrs.get("placeholder") or "Especifique"}
                continue
            numero, etiqueta, req, _for = pendiente_label or (None, "", False, None)
            ayuda = " ".join(pendiente_ayuda)
            pendiente_label, pendiente_ayuda = None, []
            c = None
            if n.tag == "input":
                t = n.attrs.get("type", "text")
                nombre = n.attrs.get("name")
                if t == "file":
                    c = campo_base("archivo", nombre, None, etiqueta, False, None)
                    c["opcional_de"] = bloques[-1]["nombre"] if bloques and "nombre" in bloques[-1] else None
                elif t == "checkbox":
                    c = campo_base("casilla", nombre, numero, etiqueta, req, ancho_label)
                elif t == "radio":
                    c = None
                else:
                    c = campo_base("texto_corto", nombre, numero, etiqueta, req or "required" in n.attrs, ancho_label)
                    if t != "text":
                        c["formato"] = t
                    if n.attrs.get("placeholder"):
                        c["placeholder"] = n.attrs.get("placeholder")
            elif n.tag == "textarea":
                c = campo_base("parrafo", n.attrs.get("name"), numero, etiqueta, req or "required" in n.attrs, ancho_label)
            elif n.tag == "select":
                nombre = n.attrs.get("name")
                if nombre == "departamento":
                    c = campo_base("departamento", nombre, numero, etiqueta, req, ancho_label)
                elif nombre == "municipio":
                    c = campo_base("municipio", nombre, numero, etiqueta, req, ancho_label)
                    c["depende_de"] = "departamento"
                else:
                    c = campo_base("seleccion", nombre, numero, etiqueta, req or "required" in n.attrs, ancho_label)
                    c["opciones"] = opciones_de_select(n)
                    if "data-otro-select" in n.attrs:
                        c["otro"] = {"valor": "Otros", "etiqueta": "Especifique"}
            elif "checkbox-group" in cl:
                cbs = n.buscar(lambda x: x.tag == "input" and x.attrs.get("type") == "checkbox")
                c = campo_base("multiple", cbs[0].attrs.get("name").replace("[]", ""), numero, etiqueta, req, ancho_label)
                c["opciones"] = [x.attrs.get("value") for x in cbs]
                if n.attrs.get("data-max"):
                    c["max"] = int(n.attrs["data-max"])
                trig = [x for x in cbs if "data-otro-trigger" in x.attrs]
                if trig:
                    c["otro"] = {"valor": trig[0].attrs.get("value"), "etiqueta": "Especifique"}
            elif "rubrica-escala" in cl:
                ins = n.buscar(lambda x: x.tag == "input")
                if ins[0].attrs.get("type") == "checkbox":
                    c = campo_base("multiple", ins[0].attrs.get("name").replace("[]", ""), numero, etiqueta, req, ancho_label)
                    c["opciones"] = [x.attrs.get("value") for x in ins]
                    c["en_linea"] = True
                else:
                    niveles = []
                    for r in ins:
                        lab = n.buscar(lambda x: x.tag == "label" and x.attrs.get("for") == r.attrs.get("id"))
                        niveles.append({"valor": r.attrs.get("value"), "texto": limpiar(lab[0].texto()) if lab else r.attrs.get("value")})
                    if [x["texto"] for x in niveles] == ["Sí", "No"]:
                        c = campo_base("si_no", ins[0].attrs.get("name"), numero, etiqueta, req, ancho_label)
                    else:
                        c = campo_base("rubrica", ins[0].attrs.get("name"), numero, etiqueta, req, ancho_label)
                        c["niveles"] = niveles
            elif "form-check" in cl and n.buscar(lambda x: x.tag == "input" and x.attrs.get("type") == "checkbox" and x.attrs.get("name") == "autoriza_tratamiento_datos_personales"):
                lab = n.buscar(lambda x: x.tag == "label")
                c = {"tipo": "consentimiento", "etiqueta": limpiar(lab[0].texto()) if lab else ""}
            elif "form-check" in cl:
                # lista vertical de radios: recoger todos los form-check consecutivos con el mismo name
                ins = n.buscar(lambda x: x.tag == "input")
                if not ins:
                    continue
                nombre = ins[0].attrs.get("name")
                ops = []
                j = i - 1
                while j < len(items) and es(items[j][0], "div", "form-check"):
                    r = items[j][0].buscar(lambda x: x.tag == "input")[0]
                    if r.attrs.get("name") != nombre:
                        break
                    ops.append(r.attrs.get("value"))
                    j += 1
                i = j
                c = campo_base("unica", nombre, numero, etiqueta, req or "required" in ins[0].attrs, ancho_label)
                c["opciones"] = ops
            elif any(x.startswith("align-items") for x in cl):
                # ranking: filas consecutivas con texto + select
                filas = []
                j = i - 1
                while j < len(items) and any(x.startswith("align-items") for x in items[j][0].clases()):
                    fila = items[j][0]
                    sel = fila.buscar(lambda x: x.tag == "select")[0]
                    txt = limpiar("".join(h for h in fila.buscar(lambda x: x.tag == "div")[0].hijos if isinstance(h, str)))
                    filas.append({"nombre": sel.attrs.get("name"), "texto": txt.lstrip("· ")})
                    j += 1
                i = j
                c = {"tipo": "ranking", "nombre": "ranking_" + filas[0]["nombre"].split("_")[0], "etiqueta": etiqueta, "items": filas,
                     "min": 1, "max": len(filas), "requerido": True}
                if numero is not None:
                    c["numero"] = numero
            if c is not None:
                if ayuda:
                    c["ayuda"] = ayuda
                bloques.append(c)
            continue
        # cualquier otra cosa: ignorar
    return bloques


if __name__ == "__main__":
    html = open(sys.argv[1], encoding="utf-8").read()
    d = convertir(html, sys.argv[2])
    print(json.dumps(d, ensure_ascii=False, indent=1))
