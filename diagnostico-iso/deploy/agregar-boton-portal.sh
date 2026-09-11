#!/usr/bin/env bash
# Agrega la tarjeta "Diagnóstico ISO 9001" a la página principal app.proyectoia.org (~/Servidor/web/index.html),
# siguiendo el mismo patrón que la tarjeta del Observatorio: se inserta al final de la rejilla de botones con las
# clases propias de la página y con el retardo de aparición siguiente al de la última tarjeta. Copia de seguridad
# antes de tocar nada; nginx sirve el archivo tal cual, no hay que reiniciar nada.
# Uso:  bash deploy/agregar-boton-portal.sh [ruta/al/index.html]
set -euo pipefail
WEB="${1:-$HOME/Servidor/web/index.html}"
SNIPPET="$(cd "$(dirname "$0")" && pwd)/boton-diagnostico.html"
[ -f "$WEB" ] || { echo "No se encontró $WEB. Pase la ruta como argumento."; exit 1; }
if grep -q "diagnosticoiso.proyectoia.org" "$WEB"; then echo "La página ya enlaza al Diagnóstico ISO 9001. No se hace nada."; exit 0; fi
COPIA="$WEB.bak-$(date +%Y%m%d-%H%M%S)"
cp "$WEB" "$COPIA"
python3 - "$WEB" "$SNIPPET" <<'PY'
import re, sys
web, snip = sys.argv[1], sys.argv[2]
t = open(web, encoding='utf-8').read()
s = open(snip, encoding='utf-8').read()
s = re.sub(r'<!--.*?-->\s*', '', s, flags=re.S)
# retardo: el siguiente al mayor dN presente en la rejilla
ds = [int(x) for x in re.findall(r'class="[^"]*\baparece\b[^"]*\bd(\d+)\b', t)]
d = (max(ds) + 1) if ds else 1
s = re.sub(r'\bd9\b', 'd%d' % d, s, count=1)
m = re.search(r'<section[^>]*rejilla-botones[^>]*>', t)
if not m: sys.exit('AVISO: no se encontró la sección rejilla-botones en ' + web)
fin = t.find('</section>', m.end())
if fin < 0: sys.exit('AVISO: la sección rejilla-botones no cierra')
t = t[:fin] + s + t[fin:]
open(web, 'w', encoding='utf-8').write(t)
print('Tarjeta agregada con retardo d%d' % d)
PY
echo "Página actualizada: $WEB"
echo "Copia de seguridad: $COPIA"
echo "Revise app.proyectoia.org en el navegador. Para deshacer:  cp \"$COPIA\" \"$WEB\""
