#!/usr/bin/env bash
# Prueba de extremo a extremo con la Solucion Automatizada simulada en Flask (misma estructura que mintic1519:
# wsgi.app, web.app.csrf, src.models.user.User con bcrypt, Flask-Login, src.services.audit_service).
# Monta wsgi_observatorio.py SIN modificar la aplicacion. El Catalogo se simula en Node.
set -uo pipefail
cd "$(dirname "$0")/.."
# Interprete de Python con Flask, Flask-Login, Flask-WTF, Flask-SQLAlchemy y bcrypt.
# Se puede fijar con PY=/ruta/al/python. Si no, se busca uno que ya tenga esas librerias.
if [ -z "${PY:-}" ]; then
  for c in .venv/bin/python ../../.venv/bin/python python3; do
    [ -x "$c" ] || command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c "import flask, flask_login, flask_wtf, flask_sqlalchemy, bcrypt" >/dev/null 2>&1 && { PY=$c; break; }
  done
fi
if [ -z "${PY:-}" ]; then
  echo "No se encontró un Python con las librerías de la prueba. Prepare uno así:"
  echo "  python3 -m venv .venv && .venv/bin/pip install flask flask-login flask-wtf flask-sqlalchemy bcrypt"
  echo "y vuelva a ejecutar esta prueba (o indique el suyo con PY=/ruta/al/python)."
  exit 1
fi
APPDIR=../conectores/mintic1519/prueba
T=$(mktemp -d)
PIDS=()
limpiar() { for p in "${PIDS[@]:-}"; do kill -9 "$p" 2>/dev/null || true; done; rm -rf "$T"; }
trap limpiar EXIT
fallo() { echo "FALLO: $*"; [ -f "$T/flask.log" ] && { echo "--- flask"; tail -15 "$T/flask.log"; }; exit 1; }
paso() { echo; echo "== $*"; }

export RUTA_BD="$T/portal.sqlite" PUERTO=8100 URL_PUBLICA=http://127.0.0.1:8100 \
  CLAVE_SESION=clave-de-prueba-suficientemente-larga-0123456789 MINUTOS_RECOLECCION=0 \
  ADMINISTRADORES=jvergaras@unicartagena.edu.co \
  APP_SOLUCION_NOMBRE="Solución Automatizada" APP_SOLUCION_URL=http://127.0.0.1:8101 APP_SOLUCION_CONECTOR=http://127.0.0.1:8101/observatorio-conector APP_SOLUCION_SECRETO=sek APP_SOLUCION_ORDEN=1 \
  APP_CATALOGO_NOMBRE="Catálogo de IA" APP_CATALOGO_URL=http://127.0.0.1:8102 APP_CATALOGO_CONECTOR=http://127.0.0.1:8102/observatorio-conector APP_CATALOGO_SECRETO=sec2 APP_CATALOGO_ORDEN=2
N="node --no-warnings"

arranca_solucion() { # $1 = 0|1 (conector apagado/encendido)
  ( cd "$APPDIR" && OBS_CONECTOR_ACTIVO=$1 OBS_CONECTOR_SECRETO=sek DATABASE_URL="sqlite:///$T/mintic.sqlite" \
    exec $PY -c "from wsgi_observatorio import app; app.run(host='127.0.0.1', port=8101)" >>"$T/flask.log" 2>&1 ) &
  SOL_PID=$!; PIDS+=("$SOL_PID")
}
espera() { for _ in $(seq 1 40); do curl -s -o /dev/null "$1" && return 0; sleep 0.25; done; return 1; }

# Catalogo (Node) y portal, activos toda la prueba
OBS_CONECTOR_ACTIVO=1 $N test/app-simulada.js 8102 "Catálogo de IA" sec2 >/dev/null 2>&1 & PIDS+=($!)
$N src/server.js >"$T/portal.log" 2>&1 & PIDS+=($!)
espera http://127.0.0.1:8100/salud || fallo "el portal no arrancó"

paso "Solución Automatizada (Flask) con el conector APAGADO, arrancada con wsgi_observatorio:app"
arranca_solucion 0
espera http://127.0.0.1:8101/admin/login || fallo "la Solución (Flask) no arrancó"
curl -s -o /dev/null -w '%{http_code}' -c "$T/a.txt" -d 'email=jmartinez@cartagena.gov.co&password=Clave.2026' http://127.0.0.1:8101/admin/login | grep -q 302 || fallo "ingreso directo en Flask"
curl -s -b "$T/a.txt" http://127.0.0.1:8101/admin/ | grep -q "Sesión de: Julián" || fallo "sesión directa en Flask"
echo "la aplicación Flask funciona sola con su propio ingreso"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8101/observatorio-conector)" = 404 ] || fallo "conector apagado debería dar 404"
[ "$(curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8101/observatorio-conector?accion=sso&token=x.y')" = 404 ] || fallo "sso apagado debería dar 404"
echo "el conector apagado es invisible (404) en verificación y en apertura de sesión"
[ "$(curl -s -o /dev/null -w '%{http_code}' -c "$T/q.txt" -d 'usuario=jmartinez@cartagena.gov.co&clave=Clave.2026' http://127.0.0.1:8100/ingresar)" = 303 ] || fallo "el portal debería verificar contra el Catálogo"
curl -s -b "$T/q.txt" http://127.0.0.1:8100/escritorio | grep -q "Sin vincular" || fallo "la Solución debería quedar sin vincular"
echo "con la Solución apagada el portal verifica contra el Catálogo y la Solución queda sin vincular"
kill -9 "$SOL_PID" 2>/dev/null; wait "$SOL_PID" 2>/dev/null; sleep 0.5

paso "Solución Automatizada (Flask) con el conector ENCENDIDO"
arranca_solucion 1
espera http://127.0.0.1:8101/admin/login || fallo "la Solución (Flask) no reinició"
[ "$(curl -s -o /dev/null -w '%{http_code}' -d 'usuario=jmartinez@cartagena.gov.co&clave=mala' http://127.0.0.1:8100/ingresar)" = 401 ] || fallo "clave incorrecta aceptada"
[ "$(curl -s -o /dev/null -w '%{http_code}' -c "$T/p.txt" -d 'usuario=jmartinez@cartagena.gov.co&clave=Clave.2026' http://127.0.0.1:8100/ingresar)" = 303 ] || fallo "ingreso al portal con la clave bcrypt de la Solución"
curl -s -b "$T/p.txt" http://127.0.0.1:8100/escritorio | grep -q "Julián" || fallo "escritorio"
echo "ingreso al portal con el correo y la clave bcrypt de la Solución Automatizada"

paso "Abrir la Solución desde el portal con la sesión Flask-Login ya iniciada"
DEST=$(curl -s -o /dev/null -w '%{redirect_url}' -b "$T/p.txt" http://127.0.0.1:8100/abrir/solucion)
[ "$(curl -s -c "$T/f.txt" -o /dev/null -w '%{http_code}' "$DEST")" = 303 ] || fallo "el conector Flask no abrió la sesión"
curl -s -b "$T/f.txt" http://127.0.0.1:8101/admin/ | grep -q "Sesión de: Julián" || fallo "Flask no reconoce la sesión abierta por el portal"
echo "la Solución reconoce la sesión creada con login_user desde el conector, sin pedir clave"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$DEST")" = 401 ] || fallo "token reutilizado aceptado"
echo "el token de un solo uso se rechaza al reutilizarlo"

paso "Recolección de datos para el cuadro de mando (solo lectura)"
$N src/cli.js recolectar > "$T/rec.json" 2>/dev/null
for c in entidades evaluaciones consolidaciones usuarios; do grep -q "\"conjunto\": \"$c\"" "$T/rec.json" || fallo "falta el conjunto $c de la Solución"; done
[ "$(grep -c '"estado": "ok"' "$T/rec.json")" = 6 ] || { cat "$T/rec.json"; fallo "se esperaban 6 conjuntos ok (4 Solución + 2 Catálogo)"; }
curl -s -o /dev/null -c "$T/adm.txt" -d 'usuario=jvergaras@unicartagena.edu.co&clave=Admin.2026' http://127.0.0.1:8100/ingresar
curl -s -b "$T/adm.txt" http://127.0.0.1:8100/tablero | grep -q "Evaluaciones de cumplimiento realizadas" || fallo "el tablero no muestra evaluaciones"
curl -s -b "$T/adm.txt" http://127.0.0.1:8100/tablero | grep -q "Entidades territoriales registradas" || fallo "el tablero no muestra entidades"
echo "el cuadro de mando muestra entidades, evaluaciones, consolidados y usuarios de la Solución"

echo; echo "TODAS LAS PRUEBAS PASARON (Flask)"
