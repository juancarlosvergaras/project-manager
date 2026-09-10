"""Extrae la estructura de un formulario Laravel (pasos, secciones, campos) a texto legible."""
import sys, re, json
from html.parser import HTMLParser


class Nodo:
    def __init__(self, tag, attrs, padre=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.hijos = []
        self.padre = padre

    def texto(self):
        partes = []
        for h in self.hijos:
            partes.append(h if isinstance(h, str) else h.texto())
        return re.sub(r"\s+", " ", "".join(partes)).strip()

    def clases(self):
        return self.attrs.get("class", "").split()

    def buscar(self, pred):
        res = []
        for h in self.hijos:
            if isinstance(h, Nodo):
                if pred(h):
                    res.append(h)
                res.extend(h.buscar(pred))
        return res


VACIOS = {"input", "br", "img", "meta", "link", "hr"}


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.raiz = Nodo("raiz", [])
        self.actual = self.raiz
        self.saltar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.saltar += 1
        n = Nodo(tag, attrs, self.actual)
        self.actual.hijos.append(n)
        if tag not in VACIOS:
            self.actual = n

    def handle_startendtag(self, tag, attrs):
        self.actual.hijos.append(Nodo(tag, attrs, self.actual))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.saltar -= 1
        n = self.actual
        while n is not None and n.tag != tag:
            n = n.padre
        if n is not None and n.padre is not None:
            self.actual = n.padre

    def handle_data(self, data):
        if self.saltar == 0 and data.strip():
            self.actual.hijos.append(data)


def volcar(n, prof=0, salida=None):
    """Volcado compacto: solo nodos con texto o campos."""
    cl = n.clases()
    tag = n.tag
    linea = None
    if tag in ("input", "select", "textarea"):
        t = n.attrs.get("type", tag)
        linea = f"[{t}] name={n.attrs.get('name')} id={n.attrs.get('id')} value={n.attrs.get('value')!r} req={'required' in n.attrs} ph={n.attrs.get('placeholder')!r}"
        if tag == "select":
            ops = [(o.attrs.get("value"), o.texto()) for o in n.buscar(lambda x: x.tag == "option")]
            linea += " opciones=" + json.dumps(ops, ensure_ascii=False)
        if n.attrs.get("data-otros") or any(k.startswith("data-") for k in n.attrs):
            linea += " data=" + json.dumps({k: v for k, v in n.attrs.items() if k.startswith("data-")}, ensure_ascii=False)
    elif tag in ("h1", "h2", "h3", "h4", "h5", "h6", "label", "p", "li", "small", "span", "strong", "button", "a", "th", "td", "legend", "option"):
        txt = n.texto()
        if txt and tag != "option":
            extra = ""
            if tag == "label":
                extra = f" for={n.attrs.get('for')}"
            if tag == "a":
                extra = f" href={n.attrs.get('href')}"
            if tag == "button":
                extra = f" type={n.attrs.get('type')} data={ {k:v for k,v in n.attrs.items() if k.startswith('data-')} }"
            linea = f"<{tag} .{'.'.join(cl)}{extra}> {txt}"
            # No bajar más: el texto ya está.
            print("  " * prof + linea)
            return
    elif tag in ("div", "section", "form", "fieldset", "ul", "ol", "table", "tr", "nav", "header", "footer", "main", "body"):
        interesantes = [c for c in cl if c not in ("row", "col-12", "mb-3", "mb-2", "mb-4", "mt-2", "d-block", "text-muted")]
        if interesantes or tag in ("form", "section", "fieldset", "table", "header", "footer"):
            linea = f"<{tag} .{'.'.join(interesantes)} id={n.attrs.get('id')}" + (f" data={ {k:v for k,v in n.attrs.items() if k.startswith('data-')} }" if any(k.startswith("data-") for k in n.attrs) else "") + ">"
    if linea:
        print("  " * prof + linea)
        prof += 1
    for h in n.hijos:
        if isinstance(h, Nodo):
            volcar(h, prof)
        elif h.strip() and tag in ("div", "section", "form", "fieldset", "td", "th"):
            print("  " * prof + "· " + re.sub(r"\s+", " ", h).strip())


if __name__ == "__main__":
    html = open(sys.argv[1], encoding="utf-8").read()
    p = Parser()
    p.feed(html)
    cuerpo = p.raiz.buscar(lambda x: x.tag == "body")
    volcar(cuerpo[0] if cuerpo else p.raiz)
