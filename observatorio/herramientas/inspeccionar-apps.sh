#!/usr/bin/env bash
# Inspeccion de solo lectura de las aplicaciones del proyecto en el servidor (Mac mini).
# No modifica ningun archivo. Redacta valores de claves, contrasenas, tokens y secretos.
# Uso:  bash inspeccionar-apps.sh /ruta/a/solucion /ruta/a/catalogoia > inspeccion.txt
# Si no conoce las rutas, ejecute sin argumentos y el script intentara localizarlas.

set -u
redactar() { sed -E 's/((PASS|PASSWORD|SECRET|KEY|TOKEN|CLAVE|CONTRASE|SALT|DSN|URI|URL)[A-Za-z_]*\s*[=:]\s*)["'"'"']?[^"'"'"' ]+/\1[REDACTADO]/Ig'; }
sec() { printf '\n==================== %s ====================\n' "$1"; }

sec "SISTEMA"
uname -a; sw_vers 2>/dev/null; echo "Fecha: $(date)"
echo "Usuario: $(whoami)"

sec "SERVICIOS EN ESCUCHA (puertos web y de base de datos)"
(sudo -n lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null || lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null) | awk 'NR==1 || /:(80|443|3000|3001|4000|5000|5173|8000|8080|8443|3306|5432|27017|6379|1433)\b/' | head -60

sec "PROCESOS DE APLICACION"
ps -axo pid,user,etime,command | grep -Ei 'node|npm|pm2|php|python|gunicorn|uvicorn|django|flask|ruby|rails|java|dotnet|caddy|nginx|httpd|apache|docker|mysql|mariadb|postgres|mongo' | grep -v grep | head -60

sec "GESTORES DE PROCESOS Y CONTENEDORES"
command -v pm2 >/dev/null && pm2 ls 2>/dev/null
command -v docker >/dev/null && docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null
launchctl list 2>/dev/null | grep -Ei 'proyecto|solucion|catalogo|node|php|nginx|caddy|httpd|mysql|postgres' | head -20

sec "SERVIDOR WEB Y DOMINIOS"
for f in /etc/nginx/nginx.conf /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf /opt/homebrew/etc/nginx/nginx.conf /opt/homebrew/etc/nginx/servers/* /usr/local/etc/nginx/servers/* /etc/apache2/httpd.conf /opt/homebrew/etc/httpd/httpd.conf /opt/homebrew/etc/httpd/extra/httpd-vhosts.conf /etc/caddy/Caddyfile /opt/homebrew/etc/Caddyfile ~/Caddyfile; do
  [ -f "$f" ] && { echo "--- $f"; grep -Ei 'server_name|proxy_pass|root |listen|ServerName|DocumentRoot|ProxyPass|reverse_proxy|proyectoia|solucion|catalogo' "$f" | head -40; }
done
command -v cloudflared >/dev/null && { echo "--- cloudflared"; ls ~/.cloudflared 2>/dev/null; grep -Ei 'hostname|service' ~/.cloudflared/*.yml 2>/dev/null; }

RUTAS=("$@")
if [ ${#RUTAS[@]} -eq 0 ]; then
  sec "BUSCANDO CARPETAS DE LAS APLICACIONES"
  while IFS= read -r d; do RUTAS+=("$d"); done < <(find ~ /var/www /srv /opt /Users/Shared -maxdepth 4 -type d \( -iname '*solucion*' -o -iname '*catalogo*' -o -iname '*proyectoia*' \) 2>/dev/null | grep -v node_modules | head -10)
  printf '%s\n' "${RUTAS[@]}"
fi

for APP in "${RUTAS[@]}"; do
  [ -d "$APP" ] || continue
  sec "APLICACION: $APP"
  echo "--- Archivos de primer nivel"; ls -la "$APP" | head -50
  echo "--- Manifiestos y senales de tecnologia"
  for f in package.json composer.json requirements.txt pyproject.toml Pipfile manage.py Gemfile go.mod pom.xml *.csproj Dockerfile docker-compose.yml docker-compose.yaml next.config.js next.config.mjs nuxt.config.ts vite.config.js vite.config.ts angular.json artisan wp-config.php index.php app.py main.py server.js app.js index.js; do
    for m in "$APP"/$f; do [ -f "$m" ] && { echo ">>> $m"; head -60 "$m" | redactar; }; done
  done
  echo "--- Archivos de configuracion (valores sensibles redactados)"
  for f in .env .env.local .env.production config.php config/database.php config/database.yml settings.py appsettings.json; do
    for m in "$APP"/$f "$APP"/*/$f; do [ -f "$m" ] && { echo ">>> $m"; grep -vE '^\s*#' "$m" | redactar | head -60; }; done
  done
  echo "--- Archivos relacionados con autenticacion y sesiones (nombres)"
  grep -rIlE --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=.git --exclude-dir=dist --exclude-dir=build -i 'login|password_verify|bcrypt|argon|passport|jsonwebtoken|express-session|session_start|authenticate|django.contrib.auth|check_password' "$APP" 2>/dev/null | head -25
  echo "--- Esquema de usuarios (definiciones encontradas)"
  grep -rIhE --exclude-dir=node_modules --exclude-dir=vendor --exclude-dir=.git -i 'CREATE TABLE[^;]*(user|usuario)|Schema\(|model User|class User|class Usuario|mongoose\.model\(.(User|Usuario)' "$APP" 2>/dev/null | head -15
  echo "--- Tamano y dependencias"
  du -sh "$APP" 2>/dev/null
  [ -f "$APP/package.json" ] && node -e 'const p=require(process.argv[1]);console.log(JSON.stringify({dependencies:p.dependencies,scripts:p.scripts},null,1))' "$APP/package.json" 2>/dev/null
done

sec "BASES DE DATOS ACCESIBLES (solo listado, sin datos)"
command -v mysql >/dev/null && mysql -e 'SHOW DATABASES' 2>/dev/null
command -v psql >/dev/null && psql -lqt 2>/dev/null | cut -d'|' -f1
command -v mongosh >/dev/null && mongosh --quiet --eval 'db.adminCommand({listDatabases:1}).databases.map(d=>d.name)' 2>/dev/null
find "${RUTAS[@]:-$HOME}" -maxdepth 3 \( -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' \) 2>/dev/null | grep -v node_modules | head -10

sec "FIN"
echo "Revise el archivo antes de compartirlo. Los valores de claves fueron redactados, pero verifique que no quede informacion sensible."
