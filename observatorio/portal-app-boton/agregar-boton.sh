#!/usr/bin/env bash
# Agrega el boton del Observatorio a la pagina principal (Servidor/web/index.html) sin perder el original.
# Hace copia de seguridad antes de tocar nada. No reinicia servicios: nginx sirve el archivo tal cual.
set -euo pipefail
WEB="${1:-$HOME/Servidor/web/index.html}"
SNIPPET="$(dirname "$0")/boton-observatorio.html"
[ -f "$WEB" ] || { echo "No se encontró $WEB. Pase la ruta como argumento."; exit 1; }
[ -f "$SNIPPET" ] || { echo "No se encontró boton-observatorio.html junto a este script."; exit 1; }
if grep -q "observatorioia.proyectoia.org" "$WEB"; then
  echo "La página ya contiene el enlace al Observatorio. No se hace nada."; exit 0
fi
cp "$WEB" "$WEB.bak-$(date +%Y%m%d-%H%M%S)"
# Inserta la tarjeta antes del primer cierre de un contenedor de tarjetas, o al final del body si no se halla.
if grep -qiE '</main>|</section>' "$WEB"; then
  awk -v snip="$(sed 's/[&]/\\&/g' "$SNIPPET")" '
    !done && /<\/(main|section)>/ { print snip; done=1 } { print }
  ' "$WEB" > "$WEB.tmp"
else
  awk -v snip="$(sed 's/[&]/\\&/g' "$SNIPPET")" '
    /<\/body>/ { print snip } { print }
  ' "$WEB" > "$WEB.tmp"
fi
mv "$WEB.tmp" "$WEB"
echo "Botón agregado a $WEB. Copia de seguridad guardada. Revise la página y, si algo no encaja,"
echo "restaure la copia .bak. Para quitar el botón, borre el bloque o restaure la copia."
