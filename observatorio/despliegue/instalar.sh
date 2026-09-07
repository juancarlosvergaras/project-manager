#!/usr/bin/env bash
# =============================================================================
# Instalador y operador del portal del Observatorio para el servidor (Mac mini u otro con Docker).
#
# Cada paso es independiente, se puede repetir sin dano (idempotente) y tiene reversa.
# Ninguna accion modifica archivos de las aplicaciones existentes: los conectores se montan por volumen
# y el cambio de comando se aplica con un archivo de superposicion de compose que se suma con -f.
#
# Uso:
#   bash instalar.sh estado                      Muestra que hay instalado y que responde
#   bash instalar.sh portal                      Copia el portal a apps/observatorio, crea .env y lo levanta
#   bash instalar.sh tunel                       Agrega la linea a rutas.conf (no recarga el tunel)
#   bash instalar.sh tunel --recargar            Igual y ademas ejecuta scripts/tunel.sh
#   bash instalar.sh boton                       Enlaza el Observatorio desde la pagina principal
#   bash instalar.sh conector solucion|catalogo  Copia el conector (APAGADO) y levanta la app con la superposicion
#   bash instalar.sh encender solucion|catalogo  Pone OBS_CONECTOR_ACTIVO=1 y reinicia solo ese servicio
#   bash instalar.sh apagar solucion|catalogo    Pone OBS_CONECTOR_ACTIVO=0 y reinicia solo ese servicio
#   bash instalar.sh revertir portal|tunel|boton|conector solucion|conector catalogo
#
# Variables opcionales:
#   RAIZ=~/Servidor        Carpeta del servidor (por defecto ~/Servidor)
#   SIMULAR=1              Muestra lo que haria sin ejecutar docker ni tocar archivos del servidor
# =============================================================================
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$AQUI/.." && pwd)"                       # carpeta observatorio/ del repositorio
RAIZ="${RAIZ:-$HOME/Servidor}"
APPS="$RAIZ/apps"
DEST_PORTAL="$APPS/observatorio"
SIMULAR="${SIMULAR:-0}"
DOCKER="${DOCKER:-docker}"
PUERTO_PORTAL=8100
SUBDOMINIO=observatorioia

# --- utilidades -------------------------------------------------------------
azul()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
verde() { printf '\033[1;32m%s\033[0m\n' "$*"; }
rojo()  { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }
paso()  { echo; azul "== $*"; }
hacer() { if [ "$SIMULAR" = 1 ]; then echo "  [simulado] $*"; else "$@"; fi; }
existe_docker() { command -v "$DOCKER" >/dev/null 2>&1 || { rojo "No se encontró docker. En el Mac mini, OrbStack debe estar abierto."; exit 1; }; }
secreto() { if command -v openssl >/dev/null 2>&1; then openssl rand -hex 48; else node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"; fi; }
respaldo() { local f="$1"; [ -f "$f" ] || return 0; local c="$f.bak-$(date +%Y%m%d-%H%M%S)"; hacer cp "$f" "$c"; echo "  copia de seguridad: $c"; }

# Datos por aplicacion. Carpeta de la app, nombre del contenedor web, archivo de conector y comando de arranque.
datos_app() {
  case "$1" in
    solucion) APP_DIR="$APPS/mintic1519"; CONTENEDOR="mintic-web"; ARCHIVO="mintic1519/wsgi_observatorio.py"; DESTINO_ARCHIVO="wsgi_observatorio.py"
              COMANDO='gunicorn wsgi_observatorio:app -w 1 --threads 16 --timeout 0 -b 0.0.0.0:8000 --access-logfile -'; PUERTO_HOST=8010; CLAVE_ENV=APP_SOLUCION_SECRETO ;;
    catalogo) APP_DIR="$APPS/catalogoia"; CONTENEDOR="catalogoia-web"; ARCHIVO="catalogoia/servidor_observatorio.py"; DESTINO_ARCHIVO="servidor_observatorio.py"
              COMANDO='python servidor_observatorio.py'; PUERTO_HOST=8020; CLAVE_ENV=APP_CATALOGO_SECRETO ;;
    *) rojo "Aplicación desconocida: $1 (use solucion o catalogo)"; exit 1 ;;
  esac
  COMPOSE_APP="$APP_DIR/docker-compose.servidor.yml"
  SUPER="$APP_DIR/observatorio/compose.observatorio.yml"
}

# Servicio de compose cuyo container_name coincide con el contenedor web de la app.
servicio_de() {
  local compose="$1" contenedor="$2"
  [ -f "$compose" ] || { echo ""; return; }
  awk -v c="$contenedor" '
    /^[[:space:]]{2}[A-Za-z0-9_-]+:[[:space:]]*$/ { s=$1; sub(":", "", s) }
    $1 == "container_name:" && $2 == c { print s; exit }
  ' "$compose"
}

valor_env() { grep -E "^$2=" "$1" 2>/dev/null | head -1 | cut -d= -f2- ; }

# --- pasos ------------------------------------------------------------------
paso_portal() {
  paso "Portal en $DEST_PORTAL"
  existe_docker
  hacer mkdir -p "$DEST_PORTAL"
  # Copia del codigo sin pruebas ni datos. El .env existente se conserva.
  for item in Dockerfile docker-compose.servidor.yml package.json README.md .env.example src static; do
    hacer rm -rf "$DEST_PORTAL/$item"
    hacer cp -R "$REPO/portal/$item" "$DEST_PORTAL/$item"
  done
  if [ ! -f "$DEST_PORTAL/.env" ]; then
    echo "  creando .env con claves nuevas"
    local cs ss cc
    cs=$(secreto); ss=$(secreto); cc=$(secreto)
    if [ "$SIMULAR" = 1 ]; then echo "  [simulado] escribir $DEST_PORTAL/.env"; else
      sed -e "s|^CLAVE_SESION=.*|CLAVE_SESION=$cs|" \
          -e "s|^APP_SOLUCION_SECRETO=.*|APP_SOLUCION_SECRETO=$ss|" \
          -e "s|^APP_CATALOGO_SECRETO=.*|APP_CATALOGO_SECRETO=$cc|" \
          -e "s|^URL_PUBLICA=.*|URL_PUBLICA=https://$SUBDOMINIO.proyectoia.org|" \
          -e "s|^RUTA_BD=.*|RUTA_BD=/app/datos/portal.sqlite|" \
          "$REPO/portal/.env.example" > "$DEST_PORTAL/.env"
      chmod 600 "$DEST_PORTAL/.env"
    fi
    echo "  revise ADMINISTRADORES en $DEST_PORTAL/.env (correos con rol de administrador del portal)"
  else
    echo "  .env existente conservado"
  fi
  hacer "$DOCKER" compose -f "$DEST_PORTAL/docker-compose.servidor.yml" --project-directory "$DEST_PORTAL" up -d --build
  if [ "$SIMULAR" != 1 ]; then
    sleep 3
    if curl -fs "http://127.0.0.1:$PUERTO_PORTAL/salud" >/dev/null; then verde "  el portal responde en http://127.0.0.1:$PUERTO_PORTAL"; else rojo "  el portal no responde. Revise: $DOCKER logs observatorio"; exit 1; fi
  fi
}

paso_tunel() {
  paso "Ruta del túnel en $RAIZ/rutas.conf"
  local rutas="$RAIZ/rutas.conf"
  [ -f "$rutas" ] || { rojo "No existe $rutas"; exit 1; }
  if grep -qE "^$SUBDOMINIO[[:space:]]" "$rutas"; then echo "  la línea ya existe"; else
    respaldo "$rutas"
    if [ "$SIMULAR" = 1 ]; then echo "  [simulado] agregar: $SUBDOMINIO $PUERTO_PORTAL   publico"; else printf '%s %s   publico\n' "$SUBDOMINIO" "$PUERTO_PORTAL" >> "$rutas"; fi
    verde "  línea agregada: $SUBDOMINIO $PUERTO_PORTAL   publico"
  fi
  if [ "${1:-}" = "--recargar" ]; then
    [ -x "$RAIZ/scripts/tunel.sh" ] || { rojo "No se encontró $RAIZ/scripts/tunel.sh"; exit 1; }
    hacer bash "$RAIZ/scripts/tunel.sh"
  else
    echo "  para publicar, ejecute: bash $RAIZ/scripts/tunel.sh   (o repita este paso con --recargar)"
    echo "  y cree el registro DNS de $SUBDOMINIO.proyectoia.org en Cloudflare si el script no lo hace"
  fi
}

paso_boton() {
  paso "Botón en la página principal ($RAIZ/web/index.html)"
  if [ "$SIMULAR" = 1 ]; then echo "  [simulado] bash $REPO/portal-app-boton/agregar-boton.sh $RAIZ/web/index.html"; else bash "$REPO/portal-app-boton/agregar-boton.sh" "$RAIZ/web/index.html"; fi
}

paso_conector() {
  local app="$1"; datos_app "$app"
  paso "Conector de $app en $APP_DIR/observatorio (APAGADO)"
  existe_docker
  [ -f "$COMPOSE_APP" ] || { rojo "No existe $COMPOSE_APP"; exit 1; }
  [ -f "$DEST_PORTAL/.env" ] || { rojo "Primero instale el portal (paso portal) para que existan los secretos"; exit 1; }
  local servicio; servicio=$(servicio_de "$COMPOSE_APP" "$CONTENEDOR")
  [ -n "$servicio" ] || { rojo "No se encontró en $COMPOSE_APP el servicio con container_name $CONTENEDOR"; exit 1; }
  local secreto_app; secreto_app=$(valor_env "$DEST_PORTAL/.env" "$CLAVE_ENV")
  [ -n "$secreto_app" ] || { rojo "El .env del portal no tiene $CLAVE_ENV"; exit 1; }
  hacer mkdir -p "$APP_DIR/observatorio"
  hacer cp "$REPO/conectores/python/observatorio_conector.py" "$APP_DIR/observatorio/observatorio_conector.py"
  hacer cp "$REPO/conectores/$ARCHIVO" "$APP_DIR/observatorio/$DESTINO_ARCHIVO"
  local activo=0
  [ -f "$SUPER" ] && activo=$(grep -oE 'OBS_CONECTOR_ACTIVO: "[01]"' "$SUPER" | grep -oE '[01]' || echo 0)
  escribir_superposicion "$servicio" "$activo" "$secreto_app"
  echo "  servicio de compose: $servicio · superposición: $SUPER"
  hacer "$DOCKER" compose -f "$COMPOSE_APP" -f "$SUPER" --project-directory "$APP_DIR" up -d "$servicio"
  if [ "$SIMULAR" != 1 ]; then
    sleep 4
    local codigo; codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PUERTO_HOST/observatorio-conector" 2>/dev/null); codigo=${codigo:-000}
    if [ "$activo" = 0 ] && [ "$codigo" = 404 ]; then verde "  la aplicación responde y el conector está apagado (404), como debe ser";
    elif [ "$activo" = 1 ] && [ "$codigo" = 401 ]; then verde "  la aplicación responde y el conector está encendido (exige firma)";
    else rojo "  respuesta inesperada del conector: $codigo. Revise: $DOCKER logs $CONTENEDOR"; fi
  fi
}

escribir_superposicion() {
  local servicio="$1" activo="$2" secreto_app="$3"
  local contenido
  contenido=$(cat <<YML
# Superposición del Observatorio para $servicio. Se suma al compose original con -f, sin editarlo.
# Reversa: levantar el servicio solo con el compose original.
services:
  $servicio:
    volumes:
      - ./observatorio/$DESTINO_ARCHIVO:/app/$DESTINO_ARCHIVO:ro
      - ./observatorio/observatorio_conector.py:/app/observatorio_conector.py:ro
    environment:
      OBS_CONECTOR_ACTIVO: "$activo"
      OBS_CONECTOR_SECRETO: "$secreto_app"
    command: $COMANDO
YML
)
  if [ "$SIMULAR" = 1 ]; then echo "  [simulado] escribir $SUPER"; echo "$contenido" | sed 's/^/    /' | sed -E 's/(OBS_CONECTOR_SECRETO: ).*/\1"[oculto]"/'; else
    printf '%s\n' "$contenido" > "$SUPER"; chmod 600 "$SUPER"; fi
}

cambiar_activo() {
  local app="$1" valor="$2"; datos_app "$app"
  existe_docker
  [ -f "$SUPER" ] || { rojo "El conector de $app no está instalado. Ejecute: instalar.sh conector $app"; exit 1; }
  local servicio; servicio=$(servicio_de "$COMPOSE_APP" "$CONTENEDOR")
  local secreto_app; secreto_app=$(grep -oE 'OBS_CONECTOR_SECRETO: "[^"]+"' "$SUPER" | cut -d'"' -f2)
  paso "$( [ "$valor" = 1 ] && echo Encender || echo Apagar ) el conector de $app"
  escribir_superposicion "$servicio" "$valor" "$secreto_app"
  hacer "$DOCKER" compose -f "$COMPOSE_APP" -f "$SUPER" --project-directory "$APP_DIR" up -d "$servicio"
  [ "$SIMULAR" = 1 ] || { sleep 4; echo "  código del conector (404 apagado, 401 encendido): $(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PUERTO_HOST/observatorio-conector")"; }
}

revertir() {
  case "$1" in
    portal) paso "Revertir portal"; existe_docker
            [ -f "$DEST_PORTAL/docker-compose.servidor.yml" ] && hacer "$DOCKER" compose -f "$DEST_PORTAL/docker-compose.servidor.yml" --project-directory "$DEST_PORTAL" down
            echo "  el contenedor se detuvo. La carpeta $DEST_PORTAL y el volumen de datos se conservan; bórrelos a mano si desea eliminar todo." ;;
    tunel)  paso "Revertir ruta del túnel"; local rutas="$RAIZ/rutas.conf"; respaldo "$rutas"
            if [ "$SIMULAR" = 1 ]; then echo "  [simulado] quitar línea $SUBDOMINIO de $rutas"; else sed -i.tmp -E "/^$SUBDOMINIO[[:space:]]/d" "$rutas" && rm -f "$rutas.tmp"; fi
            echo "  ejecute bash $RAIZ/scripts/tunel.sh para aplicar" ;;
    boton)  paso "Revertir botón"; local ult; ult=$(ls -t "$RAIZ"/web/index.html.bak-* 2>/dev/null | head -1)
            [ -n "$ult" ] || { rojo "No hay copia de seguridad de index.html"; exit 1; }
            hacer cp "$ult" "$RAIZ/web/index.html"; echo "  restaurado desde $ult" ;;
    conector) local app="${2:-}"; [ -n "$app" ] || { rojo "Indique la aplicación: revertir conector solucion|catalogo"; exit 1; }
            datos_app "$app"; existe_docker; paso "Revertir conector de $app"
            local servicio; servicio=$(servicio_de "$COMPOSE_APP" "$CONTENEDOR")
            hacer "$DOCKER" compose -f "$COMPOSE_APP" --project-directory "$APP_DIR" up -d "$servicio"
            hacer rm -f "$SUPER"
            echo "  el servicio volvió a su compose original. Los archivos en $APP_DIR/observatorio quedan sin montar; bórrelos si lo desea." ;;
    *) rojo "No sé revertir '$1'"; exit 1 ;;
  esac
}

estado() {
  paso "Estado"
  printf '  %-28s %s\n' "portal (apps/observatorio)" "$([ -d "$DEST_PORTAL" ] && echo instalado || echo 'no instalado')"
  local salud; salud=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PUERTO_PORTAL/salud" 2>/dev/null); printf '  %-28s %s\n' "portal responde en $PUERTO_PORTAL" "${salud:-000}"
  printf '  %-28s %s\n' "línea en rutas.conf" "$(grep -qE "^$SUBDOMINIO[[:space:]]" "$RAIZ/rutas.conf" 2>/dev/null && echo sí || echo no)"
  printf '  %-28s %s\n' "botón en la página principal" "$(grep -q "$SUBDOMINIO.proyectoia.org" "$RAIZ/web/index.html" 2>/dev/null && echo sí || echo no)"
  for app in solucion catalogo; do
    datos_app "$app"
    local inst="no instalado" act="-" cod
    if [ -f "$SUPER" ]; then inst="instalado"; act=$(grep -oE 'OBS_CONECTOR_ACTIVO: "[01]"' "$SUPER" | grep -oE '[01]'); fi
    cod=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PUERTO_HOST/observatorio-conector" 2>/dev/null); cod=${cod:-000}
    printf '  %-28s %s · activo=%s · respuesta=%s (404 apagado, 401 encendido)\n' "conector $app" "$inst" "$act" "$cod"
  done
}

# --- despacho ---------------------------------------------------------------
case "${1:-}" in
  estado) estado ;;
  portal) paso_portal ;;
  tunel) paso_tunel "${2:-}" ;;
  boton) paso_boton ;;
  conector) paso_conector "${2:-}" ;;
  encender) cambiar_activo "${2:-}" 1 ;;
  apagar) cambiar_activo "${2:-}" 0 ;;
  revertir) revertir "${2:-}" "${3:-}" ;;
  *) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
