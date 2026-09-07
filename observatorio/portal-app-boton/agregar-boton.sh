#!/usr/bin/env bash
# Enlaza el Observatorio desde la pagina principal (Servidor/web/index.html) sin perder el original.
#
# La pagina ya tiene una tarjeta "Observatorio IA", pero es un <button> sin destino que solo muestra el
# aviso "proximamente". Este script la sustituye por la tarjeta enlazada de boton-observatorio.html,
# que usa las mismas clases y conserva el retardo de aparicion, de modo que la rejilla no cambia de aspecto
# ni de orden. Si esa tarjeta ya no existe, agrega la nueva al final de la rejilla de botones.
#
# Hace copia de seguridad antes de tocar nada y no reinicia servicios: nginx sirve el archivo tal cual.
# Para deshacer, restaure la copia .bak que se indica al terminar.
set -euo pipefail
WEB="${1:-$HOME/Servidor/web/index.html}"
SNIPPET="$(cd "$(dirname "$0")" && pwd)/boton-observatorio.html"
[ -f "$WEB" ] || { echo "No se encontró $WEB. Pase la ruta como argumento."; exit 1; }
[ -f "$SNIPPET" ] || { echo "No se encontró boton-observatorio.html junto a este script."; exit 1; }
if grep -q "observatorioia.proyectoia.org" "$WEB"; then
  echo "La página ya enlaza al Observatorio. No se hace nada."; exit 0
fi

COPIA="$WEB.bak-$(date +%Y%m%d-%H%M%S)"
cp "$WEB" "$COPIA"

awk -v snip="$SNIPPET" '
  function volcar(  linea) { while ((getline linea < snip) > 0) print linea; close(snip) }
  # 1. Sustituir la tarjeta "Observatorio IA" que hoy no lleva a ningún sitio.
  !hecho && /<button[^>]*data-nombre="Observatorio IA"/ { dentro = 1; next }
  dentro { if ($0 ~ /<\/button>/) { dentro = 0; hecho = 1; volcar() } next }
  # 2. Si no estaba, agregarla al final de la rejilla de botones.
  /<section[^>]*rejilla-botones/ { rejilla = 1 }
  rejilla && !hecho && /<\/section>/ { volcar(); hecho = 1; rejilla = 0 }
  { print }
  END { if (!hecho) { print "AVISO: no se encontró dónde insertar la tarjeta." > "/dev/stderr"; exit 1 } }
' "$WEB" > "$WEB.tmp" || { rm -f "$WEB.tmp"; mv "$COPIA" "$WEB"; echo "No se modificó nada."; exit 1; }

mv "$WEB.tmp" "$WEB"
echo "Página actualizada: $WEB"
echo "Copia de seguridad: $COPIA"
echo "Revise la página en el navegador. Para deshacer:  cp \"$COPIA\" \"$WEB\""
