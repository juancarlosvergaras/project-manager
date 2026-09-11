#!/usr/bin/env python3
"""Agrega la tarjeta "Diagnóstico ISO 9001" al portal app.proyectoia.org copiando el formato de una tarjeta existente.

Uso:
  python3 deploy/portal-agregar-tarjeta.py                      # busca el archivo del portal y aplica el cambio
  python3 deploy/portal-agregar-tarjeta.py /ruta/al/index.html  # archivo explícito
  python3 deploy/portal-agregar-tarjeta.py --ver                # solo muestra qué haría, sin modificar

Localiza la tarjeta "Gestor Proyecto" (o la de referencia indicada con --referencia), la duplica y cambia título,
descripción y enlace. Funciona con tarjetas HTML (<a ...>...</a> o <div ...>...</div>) y con listas de objetos en
JavaScript/JSON ({ titulo: 'Gestor Proyecto', ... }). Hace copia de seguridad antes de escribir.
"""
import os, re, sys, glob, shutil, time

TITULO = 'Diagnóstico ISO 9001'
DESCRIPCION = 'Cuestionario de implementación ISO 9001:2015, versiones, indicadores y brecha para la certificación.'
URL = 'https://diagnosticoiso.proyectoia.org/'
REFERENCIA = 'Gestor Proyecto'
MARCA = 'Observatorio de Riesgos IA'

args = [a for a in sys.argv[1:] if not a.startswith('--')]
solo_ver = '--ver' in sys.argv
for a in sys.argv[1:]:
    if a.startswith('--referencia='): REFERENCIA = a.split('=', 1)[1]

def buscar_archivo():
    raices = [os.path.expanduser(p) for p in ('~/Servidor', '~/Sites', '~/apps', '/usr/local/var/www', '/opt/homebrew/var/www', '/var/www')]
    cand = []
    for raiz in raices:
        if not os.path.isdir(raiz): continue
        for dp, dn, fn in os.walk(raiz):
            dn[:] = [d for d in dn if d not in ('node_modules', '.git', 'data', 'venv', '.venv') and not d.startswith('respaldo')]
            for f in fn:
                if f.endswith(('.html', '.htm', '.js', '.json', '.py', '.jinja', '.j2', '.ejs', '.vue', '.tsx', '.jsx')):
                    ruta = os.path.join(dp, f)
                    try:
                        with open(ruta, encoding='utf-8', errors='ignore') as fh: t = fh.read()
                    except OSError: continue
                    if MARCA in t and REFERENCIA in t:
                        cand.append((0 if f.endswith(('.html', '.htm')) else 1, ruta))
    cand.sort()
    return [c[1] for c in cand]

def bloque_html(t, pos):
    """Elemento HTML (a, div, article, li) más cercano que envuelve pos y contiene el texto de referencia."""
    mejor = None
    for m in re.finditer(r'<(a|div|article|li|section)\b[^>]*>', t[:pos]):
        etiqueta = m.group(1)
        ini = m.start()
        # cierre balanceado
        prof, i = 0, ini
        patron = re.compile(r'<(/?)%s\b[^>]*>' % etiqueta)
        fin = None
        for mm in patron.finditer(t, ini):
            prof += -1 if mm.group(1) else 1
            if prof == 0: fin = mm.end(); break
        if fin and fin > pos:
            frag = t[ini:fin]
            if frag.count(MARCA) == 0 and frag.count(REFERENCIA) == 1 and 'href' in frag or (frag.count(REFERENCIA) == 1 and frag.count(MARCA) == 0 and len(frag) < 2500):
                if mejor is None or (fin - ini) > (mejor[1] - mejor[0]):
                    # preferimos el bloque más grande que no incluya otras tarjetas
                    otras = sum(1 for tt in ('Catálogo IA', 'Automatizaciones', 'Gestión Documental', MARCA) if tt in frag)
                    if otras == 0: mejor = (ini, fin)
    return mejor

def bloque_objeto(t, pos):
    """Objeto {...} con llaves balanceadas que contiene pos."""
    ini = t.rfind('{', 0, pos)
    while ini != -1:
        prof, i = 0, ini
        while i < len(t):
            c = t[i]
            if c == '{': prof += 1
            elif c == '}':
                prof -= 1
                if prof == 0: break
            i += 1
        frag = t[ini:i + 1]
        if i > pos and MARCA not in frag and frag.count(REFERENCIA) == 1: return (ini, i + 1)
        ini = t.rfind('{', 0, ini)
    return None

def transformar(frag):
    nuevo = frag.replace(REFERENCIA, TITULO)
    # descripción: el texto de la tarjeta de referencia (Gestor Proyecto)
    nuevo = re.sub(r'Cronograma, entregables, riesgos y\s+reportes del proyecto IA para el Estado\.?', DESCRIPCION, nuevo)
    nuevo = re.sub(r'https?://gestor\.proyectoia\.org[^"\'\s<>]*', URL, nuevo)
    nuevo = re.sub(r'(["\'])/?gestor/?\1', r'\1' + URL + r'\1', nuevo)
    if URL not in nuevo:
        nuevo = re.sub(r'(href=["\'])[^"\']*(["\'])', r'\1' + URL + r'\2', nuevo, count=1)
    if URL not in nuevo:
        nuevo = re.sub(r'((?:url|href|enlace|link)\s*:\s*["\'])[^"\']*(["\'])', r'\1' + URL + r'\2', nuevo, count=1)
    return nuevo

def main():
    archivos = args or buscar_archivo()
    if not archivos:
        print('No se encontró el archivo del portal (busqué "%s" y "%s" en ~/Servidor, ~/Sites, ~/apps y /var/www).' % (MARCA, REFERENCIA)); sys.exit(1)
    for ruta in archivos:
        with open(ruta, encoding='utf-8') as fh: t = fh.read()
        if TITULO in t:
            print('%s: la tarjeta "%s" ya existe. Nada que hacer.' % (ruta, TITULO)); continue
        pos = t.find(REFERENCIA)
        if pos < 0: continue
        es_html = ruta.endswith(('.html', '.htm', '.jinja', '.j2', '.ejs'))
        b = (bloque_html(t, pos) if es_html else None) or bloque_objeto(t, pos) or (bloque_html(t, pos) if not es_html else None)
        if not b:
            print('%s: encontré "%s" pero no pude delimitar la tarjeta. Envíe este fragmento:' % (ruta, REFERENCIA))
            print(t[max(0, pos - 600):pos + 600]); sys.exit(2)
        frag = t[b[0]:b[1]]
        nuevo = transformar(frag)
        if URL not in nuevo:
            print('%s: no encontré dónde poner el enlace en la tarjeta de referencia. Fragmento:' % ruta); print(frag); sys.exit(2)
        # separador: si es objeto en lista, coma; si es HTML, salto de línea con la misma sangría
        linea_ini = t.rfind('\n', 0, b[0]) + 1
        sangria = re.match(r'[ \t]*', t[linea_ini:b[0]]).group(0)
        if frag.lstrip().startswith('{'):
            # {gestor},\n  {nuevo}  + resto (que empieza con la coma original o con el cierre de la lista)
            salida = t[:b[1]] + ',\n' + sangria + nuevo + t[b[1]:]
        else:
            salida = t[:b[1]] + '\n' + sangria + nuevo + t[b[1]:]
        print('== %s ==' % ruta)
        print('Tarjeta de referencia:\n' + frag[:700] + ('…' if len(frag) > 700 else ''))
        print('\nTarjeta nueva:\n' + nuevo[:700] + ('…' if len(nuevo) > 700 else ''))
        if solo_ver:
            print('\n(--ver: no se modificó el archivo)'); return
        respaldo = ruta + '.bak.' + time.strftime('%Y%m%d%H%M%S')
        shutil.copy2(ruta, respaldo)
        with open(ruta, 'w', encoding='utf-8') as fh: fh.write(salida)
        print('\nListo: tarjeta agregada en %s (copia de seguridad: %s). Recargue app.proyectoia.org.' % (ruta, respaldo))
        return
    print('No se aplicó ningún cambio.'); sys.exit(1)

if __name__ == '__main__':
    main()
