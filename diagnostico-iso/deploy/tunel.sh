#!/usr/bin/env bash
# Crea (o reutiliza) el túnel de Cloudflare "diagnosticoiso", escribe cloudflared.yml, crea el DNS
# y deja cloudflared corriendo como agente launchd del usuario. Mismo esquema por aplicación que riesgosia.
#
# Uso:  bash deploy/tunel.sh        (desde la carpeta diagnostico-iso, con el usuario normal, sin sudo)
# Variables opcionales: NOMBRE, DOMINIO, PUERTO
set -euo pipefail

APP="$(cd "$(dirname "$0")/.." && pwd)"
NOMBRE="${NOMBRE:-diagnosticoiso}"
DOMINIO="${DOMINIO:-diagnosticoiso.proyectoia.org}"
PUERTO="${PUERTO:-3050}"
CF="$(command -v cloudflared || true)"; [ -z "$CF" ] && [ -x /opt/homebrew/bin/cloudflared ] && CF=/opt/homebrew/bin/cloudflared
[ -z "$CF" ] && { echo "!! cloudflared no está instalado (brew install cloudflared)"; exit 1; }
ETIQUETA="org.proyectoia.diagnosticoiso.tunel"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"

echo "== Túnel $NOMBRE -> https://$DOMINIO -> http://localhost:$PUERTO =="

# 1. Autenticación con Cloudflare (abre el navegador solo la primera vez)
[ -f "$HOME/.cloudflared/cert.pem" ] || "$CF" tunnel login

# 2. Crear el túnel si no existe y obtener su ID
if ! "$CF" tunnel list --name "$NOMBRE" -o json 2>/dev/null | grep -q '"id"'; then
  echo "-- Creando túnel $NOMBRE"; "$CF" tunnel create "$NOMBRE" >/dev/null
fi
ID="$("$CF" tunnel list --name "$NOMBRE" -o json | tr -d '\n ' | sed -E 's/.*"id":"([^"]+)".*/\1/')"
[ -z "$ID" ] && { echo "!! No se pudo obtener el ID del túnel"; exit 1; }
CRED="$HOME/.cloudflared/$ID.json"
[ -f "$CRED" ] || { echo "!! No existe el archivo de credenciales $CRED. Elimine el túnel (cloudflared tunnel delete $NOMBRE) y ejecute de nuevo."; exit 1; }
echo "-- Túnel $NOMBRE ($ID)"

# 3. cloudflared.yml de la aplicación
cat > "$APP/cloudflared.yml" <<Y
tunnel: $ID
credentials-file: $CRED
ingress:
  - hostname: $DOMINIO
    service: http://localhost:$PUERTO
  - service: http_status:404
Y
"$CF" tunnel --config "$APP/cloudflared.yml" ingress validate
echo "-- $APP/cloudflared.yml escrito y validado"

# 4. DNS
# Se usa el UUID y --overwrite-dns: por nombre, cloudflared puede resolver a otro túnel de la cuenta.
salida="$("$CF" tunnel route dns --overwrite-dns "$ID" "$DOMINIO" 2>&1)" && echo "-- DNS: $DOMINIO -> $ID.cfargotunnel.com" || {
  echo "$salida" | grep -qi "already exists" && echo "-- DNS ya existía: $DOMINIO" || { echo "!! DNS: $salida"; echo "   Cree manualmente el CNAME diagnosticoiso -> $ID.cfargotunnel.com (proxy activado)"; }
}

# 5. Agente launchd (arranca al iniciar sesión y se reinicia si cae)
mkdir -p "$HOME/Library/LaunchAgents" "$APP/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ETIQUETA</string>
  <key>ProgramArguments</key><array>
    <string>$CF</string><string>--config</string><string>$APP/cloudflared.yml</string><string>--no-autoupdate</string><string>tunnel</string><string>run</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP/logs/tunel.log</string>
  <key>StandardErrorPath</key><string>$APP/logs/tunel.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$ETIQUETA" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "-- cloudflared en ejecución como agente launchd ($ETIQUETA)"

# 6. Verificación
for i in 1 2 3 4 5 6; do
  sleep 5
  codigo="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "https://$DOMINIO/api/config" 2>/dev/null || echo 000)"
  [ "$codigo" = "200" ] && { echo "== Listo: https://$DOMINIO responde (HTTP 200) =="; exit 0; }
done
echo "!! https://$DOMINIO respondió HTTP $codigo. El DNS puede tardar unos minutos. Registro del túnel: tail -n 30 $APP/logs/tunel.log"
exit 1
