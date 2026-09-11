#!/usr/bin/env bash
# Publica diagnosticoiso.proyectoia.org en el túnel de Cloudflare ya existente del Mac (cloudflared por archivo).
# Idempotente: si el hostname ya está, no lo duplica. Hace copia de seguridad, valida y restaura si algo falla.
#
# Uso (en el Mac, requiere sudo porque el túnel corre como root):
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/juancarlosvergaras/project-manager/main/diagnostico-iso/deploy/publicar-tunel.sh)"
# Variables opcionales: DOMINIO, PUERTO, CONFIG
set -uo pipefail

DOMINIO="${DOMINIO:-diagnosticoiso.proyectoia.org}"
PUERTO="${PUERTO:-3050}"
CONFIG="${CONFIG:-/etc/cloudflared/config.yml}"
CF="$(command -v cloudflared || true)"; [ -z "$CF" ] && [ -x /opt/homebrew/bin/cloudflared ] && CF=/opt/homebrew/bin/cloudflared
[ -z "$CF" ] && { echo "!! cloudflared no está instalado"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "!! Ejecute con sudo (el túnel corre como root y $CONFIG pertenece a root)"; exit 1; }
[ -f "$CONFIG" ] || { echo "!! No existe $CONFIG"; exit 1; }

echo "== Publicar https://$DOMINIO -> http://localhost:$PUERTO =="

# 0. La aplicación debe estar respondiendo localmente
if ! curl -fsS -m 5 "http://127.0.0.1:$PUERTO/api/config" >/dev/null; then
  echo "!! La aplicación no responde en el puerto $PUERTO. Ejecute primero deploy/instalar-macmini.sh"; exit 1
fi

# 1. Regla de ingress
RESPALDO="$CONFIG.bak.$(date +%Y%m%d%H%M%S)"
if grep -q "hostname: *$DOMINIO" "$CONFIG"; then
  echo "-- El hostname ya está en $CONFIG"
else
  cp "$CONFIG" "$RESPALDO"; echo "-- Copia de seguridad: $RESPALDO"
  perl -0pi -e 's/^(\s*)-\s*service:\s*http_status:\s*404/$1- hostname: '"$DOMINIO"'\n$1  service: http:\/\/localhost:'"$PUERTO"'\n$1- service: http_status:404/m' "$CONFIG"
  if ! grep -q "hostname: *$DOMINIO" "$CONFIG"; then
    cp "$RESPALDO" "$CONFIG"; echo "!! No se encontró la regla final 'service: http_status:404' en $CONFIG. Se restauró la copia."; echo "   Contenido actual:"; sed 's/^/   /' "$CONFIG"; exit 1
  fi
  if ! "$CF" tunnel --config "$CONFIG" ingress validate; then
    cp "$RESPALDO" "$CONFIG"; echo "!! La configuración no validó. Se restauró la copia."; exit 1
  fi
  echo "-- Regla agregada y validada"
fi

# 2. Registro DNS (CNAME hacia el túnel)
TUNEL="$(awk '/^tunnel:/{print $2}' "$CONFIG" | tr -d '"'"'"'')"
[ -z "$TUNEL" ] && { echo "!! No se encontró la línea 'tunnel:' en $CONFIG"; exit 1; }
echo "-- Túnel: $TUNEL"
dns_ok=0
salida="$("$CF" tunnel route dns "$TUNEL" "$DOMINIO" 2>&1)" && dns_ok=1
if [ $dns_ok -eq 0 ] && echo "$salida" | grep -qi "already exists"; then dns_ok=1; fi
if [ $dns_ok -eq 0 ]; then
  for cert in /Users/*/.cloudflared/cert.pem /etc/cloudflared/cert.pem; do
    [ -f "$cert" ] || continue
    salida="$("$CF" --origincert "$cert" tunnel route dns "$TUNEL" "$DOMINIO" 2>&1)" && { dns_ok=1; break; }
    echo "$salida" | grep -qi "already exists" && { dns_ok=1; break; }
  done
fi
if [ $dns_ok -eq 1 ]; then echo "-- DNS: $DOMINIO apunta al túnel"; else
  echo "!! No se pudo crear el DNS automáticamente ($salida)"
  echo "   Créelo en el panel de Cloudflare, zona proyectoia.org: CNAME  diagnosticoiso  ->  $TUNEL.cfargotunnel.com  (proxy activado)"
fi

# 3. Reiniciar cloudflared para que cargue la nueva regla
if launchctl print system/com.cloudflare.cloudflared >/dev/null 2>&1; then
  launchctl kickstart -k system/com.cloudflare.cloudflared && echo "-- cloudflared reiniciado (launchd)"
else
  pkill -f "cloudflared --config $CONFIG" && echo "-- cloudflared detenido; launchd o su supervisor debe reiniciarlo" || echo "!! No se encontró el proceso de cloudflared para reiniciar"
fi

# 4. Verificación
for i in 1 2 3 4 5 6; do
  sleep 5
  codigo="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "https://$DOMINIO/api/config" 2>/dev/null || echo 000)"
  [ "$codigo" = "200" ] && { echo "== Listo: https://$DOMINIO responde (HTTP 200) =="; exit 0; }
done
echo "!! https://$DOMINIO respondió HTTP $codigo. Si acaba de crearse el DNS puede tardar un par de minutos; pruebe de nuevo: curl -I https://$DOMINIO"
exit 1
