#!/usr/bin/env bash
# Extrae, en solo lectura, los fragmentos de codigo de la Solucion Automatizada (mintic1519) y del Catalogo de IA
# (catalogoia) que definen usuarios, verificacion de clave y sesion, mas la convencion de rutas del tunel.
# No modifica nada. Redacta claves y secretos. Uso: bash inspeccionar-codigo.sh > codigo.txt
S="$HOME/Servidor"
redactar() { sed -E 's/((PASS|PASSWORD|SECRET|KEY|TOKEN|CLAVE|CONTRASE|SALT|DATABASE_URL)[A-Za-z_]*\s*[=:]\s*)["'"'"']?[^"'"'"' ]+/\1[REDACTADO]/Ig'; }
sec() { printf '\n==================== %s ====================\n' "$1"; }
ver() { [ -f "$1" ] && { echo ">>> $1"; redactar < "$1" | head -${2:-120}; echo; } || echo "(no existe $1)"; }
busca() { grep -rnI --include='*.py' -E "$2" "$1" 2>/dev/null | grep -v -E 'tests?/|migrations/|\.bak' | redactar | head -${3:-40}; }

sec "CONVENCIONES DEL SERVIDOR"
ver "$S/CLAUDE.md" 400
ver "$S/rutas.conf" 60
ver "$S/scripts/tunel.sh" 120
ls "$S/scripts"

sec "SOLUCION AUTOMATIZADA (mintic1519) · arranque y compose"
ver "$S/apps/mintic1519/wsgi.py" 80
ver "$S/apps/mintic1519/docker-compose.servidor.yml" 120
ls "$S/apps/mintic1519/src"; ls "$S/apps/mintic1519/src"/* 2>/dev/null | head -60

sec "SOLUCION AUTOMATIZADA · fabrica de la aplicacion y login"
busca "$S/apps/mintic1519/src" 'def create_app|LoginManager|login_manager|user_loader|Flask\(' 30
echo "--- modelo de usuario"
F=$(grep -rlI --include='*.py' -E 'class (User|Usuario)\b' "$S/apps/mintic1519/src" 2>/dev/null | grep -v migrations | head -1)
[ -n "$F" ] && { echo ">>> $F"; redactar < "$F" | head -160; }
echo "--- rutas de autenticacion"
F2=$(grep -rlI --include='*.py' -E 'login_user\(|check_password|bcrypt' "$S/apps/mintic1519/src" 2>/dev/null | grep -v migrations | head -3)
for f in $F2; do echo ">>> $f"; redactar < "$f" | grep -n -E 'route|login_user|check_password|bcrypt|def |session\[|remember|email|username' | head -60; done
echo "--- tablas principales (para el tablero)"
busca "$S/apps/mintic1519/src" '__tablename__' 40

sec "CATALOGO DE IA (catalogoia) · arranque y compose"
ver "$S/apps/catalogoia/arranque.sh" 60
ver "$S/apps/catalogoia/servidor.py" 80
ver "$S/apps/catalogoia/docker-compose.servidor.yml" 80
echo "--- estructura de app.py"
wc -l "$S/apps/catalogoia/app.py"
grep -n -E '^(from|import) |^app *=|Flask\(|secret_key|SECRET_KEY|def [a-z_]+\(|@app\.route|session\[|session\.get|check_password|hashlib|pbkdf2|bcrypt|werkzeug\.security|CREATE TABLE|sqlite3\.connect|login_required|ADMIN_USER' "$S/apps/catalogoia/app.py" 2>/dev/null | redactar | head -150

sec "PORTAL ESTATICO ACTUAL (app.proyectoia.org)"
ls "$S/web" | head -30
echo "--- identidad compartida de gestor/documental/casos/modelado (para la fase siguiente)"
grep -n -E 'def |json|hash|pbkdf2|sha|clave|token|cookie' "$S/apps/gestor/identidad.py" 2>/dev/null | head -40
[ -f "$S/apps/gestor/auth.py" ] && grep -n -E 'def |hash|pbkdf2|sha|cookie|token' "$S/apps/gestor/auth.py" | head -40

sec "FIN"
