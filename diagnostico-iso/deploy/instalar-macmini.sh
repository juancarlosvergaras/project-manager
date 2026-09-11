#!/usr/bin/env bash
# Instala o actualiza Diagnóstico ISO 9001 en un Mac (probado para macOS con Homebrew) y lo deja
# corriendo como servicio de usuario (launchd) en el puerto indicado. Idempotente: se puede ejecutar
# tantas veces como se quiera para actualizar a la última versión de la rama.
#
# Uso (desde una terminal o sesión SSH en el Mac):
#   curl -fsSL https://raw.githubusercontent.com/juancarlosvergaras/project-manager/main/diagnostico-iso/deploy/instalar-macmini.sh | bash
# Variables opcionales: RAMA (rama de git), PUERTO (puerto local), DESTINO (carpeta de instalación)
set -euo pipefail

REPO="https://github.com/juancarlosvergaras/project-manager.git"
RAMA="${RAMA:-main}"
PUERTO="${PUERTO:-3050}"
DESTINO="${DESTINO:-$HOME/apps/project-manager}"
APP="$DESTINO/diagnostico-iso"
ETIQUETA="org.proyectoia.diagnosticoiso"
PLIST="$HOME/Library/LaunchAgents/$ETIQUETA.plist"
DOMINIO="diagnosticoiso.proyectoia.org"

echo "== Diagnóstico ISO 9001 · instalación en $(hostname) =="

# 1. Node.js 22.13 o superior
necesita_node=1
if command -v node >/dev/null 2>&1; then
  v=$(node -v | sed 's/^v//'); mayor=${v%%.*}; menor=$(echo "$v" | cut -d. -f2)
  if [ "$mayor" -gt 22 ] || { [ "$mayor" -eq 22 ] && [ "$menor" -ge 13 ]; }; then necesita_node=0; fi
fi
if [ "$necesita_node" -eq 1 ]; then
  if ! command -v brew >/dev/null 2>&1; then echo "Instale Homebrew (https://brew.sh) o Node.js 22.13+ y vuelva a ejecutar."; exit 1; fi
  echo "-- Instalando Node.js 22 con Homebrew"
  brew install node@22 >/dev/null
  brew link --overwrite --force node@22 >/dev/null || true
fi
NODE_BIN="$(command -v node)"
echo "-- Node.js $(node -v) en $NODE_BIN"

# 2. Código fuente
mkdir -p "$(dirname "$DESTINO")"
if [ -d "$DESTINO/.git" ]; then
  echo "-- Actualizando repositorio ($RAMA)"
  git -C "$DESTINO" fetch --quiet origin "$RAMA"
  git -C "$DESTINO" checkout --quiet "$RAMA"
  git -C "$DESTINO" reset --quiet --hard "origin/$RAMA"
else
  echo "-- Clonando repositorio ($RAMA) en $DESTINO"
  git clone --quiet --branch "$RAMA" "$REPO" "$DESTINO"
fi

# 3. Configuración (.env) — se crea una sola vez y no se sobreescribe
mkdir -p "$APP/data"
if [ ! -f "$APP/.env" ]; then
  echo "-- Creando $APP/.env"
  SECRETO=$(openssl rand -hex 32)
  CLAVE=$(openssl rand -base64 12 | tr -d '/+=' | cut -c1-14)
  cat > "$APP/.env" <<ENV
PORT=$PUERTO
HOST=127.0.0.1
NODE_ENV=production
BASE_URL=https://$DOMINIO
DB_PATH=$APP/data/diagnostico.sqlite
SESSION_SECRET=$SECRETO
SESSION_DAYS=14
AUTH_MODE=mixto
ADMIN_EMAIL=admin@proyectoia.org
ADMIN_PASSWORD=$CLAVE
ADMIN_NOMBRE=Administrador
GESTOR_NOMBRE=Gestor ProyectoIA
GESTOR_URL=https://gestor.proyectoia.org
# Complete estas variables cuando defina el contrato con gestor.proyectoia.org (ver README)
GESTOR_LOGIN_URL=
GESTOR_USERINFO_URL=
GESTOR_JWT_SECRET=
APP_PROYECTOIA_URL=https://app.proyectoia.org
ENV
  echo "   Usuario inicial: admin@proyectoia.org   Contraseña: $CLAVE   (guárdela; también está en $APP/.env)"
fi

# 4. Servicio launchd (arranca al iniciar sesión y se reinicia si falla)
mkdir -p "$HOME/Library/LaunchAgents" "$APP/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ETIQUETA</string>
  <key>ProgramArguments</key><array>
    <string>$NODE_BIN</string><string>--no-warnings=ExperimentalWarning</string><string>--env-file=.env</string><string>server/index.js</string>
  </array>
  <key>WorkingDirectory</key><string>$APP</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP/logs/salida.log</string>
  <key>StandardErrorPath</key><string>$APP/logs/error.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$ETIQUETA" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 2
if curl -fsS "http://127.0.0.1:$PUERTO/api/config" >/dev/null; then
  echo "-- Servicio activo en http://127.0.0.1:$PUERTO"
else
  echo "!! El servicio no respondió. Revise $APP/logs/error.log"; exit 1
fi

# 5. Publicación del dominio
echo
echo "== Publicar https://$DOMINIO =="
if command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared está instalado. Agregue el hostname público al túnel que ya usa para app y gestor:"
  echo "  · Túnel administrado desde el panel de Cloudflare (Zero Trust > Networks > Tunnels > su túnel > Public Hostname > Add):"
  echo "      Subdomain: diagnosticoiso   Domain: proyectoia.org   Service: HTTP  localhost:$PUERTO"
  if [ -f "$HOME/.cloudflared/config.yml" ]; then
    echo "  · Túnel por archivo ($HOME/.cloudflared/config.yml): añada bajo ingress, antes de la regla final http_status:404:"
    echo "      - hostname: $DOMINIO"
    echo "        service: http://localhost:$PUERTO"
    echo "    y luego:  cloudflared tunnel route dns <NOMBRE_DEL_TUNEL> $DOMINIO  y reinicie cloudflared."
  fi
else
  echo "No se detectó cloudflared. Opciones:"
  echo "  A) Cloudflare Tunnel (recomendado, mismo esquema que app y gestor):"
  echo "       brew install cloudflared && cloudflared tunnel login"
  echo "       cloudflared tunnel create diagnosticoiso"
  echo "       cloudflared tunnel route dns diagnosticoiso $DOMINIO"
  echo "       cloudflared tunnel --url http://localhost:$PUERTO run diagnosticoiso   (o instálelo como servicio: sudo cloudflared service install)"
  echo "  B) Prueba inmediata con Tailscale Funnel (URL pública *.ts.net, sin dominio propio):"
  echo "       tailscale funnel --bg $PUERTO"
fi
echo
echo "Listo. Para actualizar a la última versión ejecute este mismo script de nuevo."
