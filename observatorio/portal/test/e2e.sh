#!/usr/bin/env bash
# Prueba de extremo a extremo con dos aplicaciones simuladas.
# 1. Con el conector apagado, las aplicaciones funcionan solas y el portal no puede verificar claves.
# 2. Con el conector encendido, el usuario ingresa al portal con la clave de la aplicacion, abre la aplicacion
#    con la sesion iniciada, vincula la segunda aplicacion y el portal recolecta datos para el tablero.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'kill $(jobs -p) 2>/dev/null || true; rm -rf "$T"' EXIT
export RUTA_BD="$T/portal.sqlite" PUERTO=8100 URL_PUBLICA=http://127.0.0.1:8100 CLAVE_SESION=clave-de-prueba-suficientemente-larga-0123456789 MINUTOS_RECOLECCION=0
export ADMINISTRADORES=jvergaras@unicartagena.edu.co
export APP_SOLUCION_NOMBRE="Solución Automatizada" APP_SOLUCION_URL=http://127.0.0.1:8101 APP_SOLUCION_CONECTOR=http://127.0.0.1:8101/observatorio-conector APP_SOLUCION_SECRETO=secreto-solucion-prueba APP_SOLUCION_ORDEN=1
export APP_CATALOGO_NOMBRE="Catálogo de IA" APP_CATALOGO_URL=http://127.0.0.1:8102 APP_CATALOGO_CONECTOR=http://127.0.0.1:8102/observatorio-conector APP_CATALOGO_SECRETO=secreto-catalogo-prueba APP_CATALOGO_ORDEN=2
N="node --no-warnings"
fallo() { echo "FALLO: $*"; exit 1; }
paso() { echo; echo "== $*"; }

paso "Aplicaciones simuladas con el conector APAGADO"
OBS_CONECTOR_ACTIVO=0 $N test/app-simulada.js 8101 "Solución Automatizada" secreto-solucion-prueba & 
OBS_CONECTOR_ACTIVO=0 $N test/app-simulada.js 8102 "Catálogo de IA" secreto-catalogo-prueba &
$N src/server.js & sleep 1.2
curl -sf http://127.0.0.1:8101/ | grep -q "Sin sesión" || fallo "la aplicación 1 no responde de forma independiente"
curl -s -c "$T/a.txt" -o /dev/null -w '%{http_code}' -d 'usuario=jmartinez&clave=Clave.2026' http://127.0.0.1:8101/login | grep -q 303 || fallo "ingreso directo en la aplicación 1"
curl -s -b "$T/a.txt" http://127.0.0.1:8101/ | grep -q "Sesión de: Julián" || fallo "sesión directa en la aplicación 1"
echo "las aplicaciones funcionan solas, con su propio ingreso"
curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8101/observatorio-conector | grep -q 404 || fallo "el conector apagado debería responder 404"
echo "el conector apagado es invisible (404)"
C=$(curl -s -o /dev/null -w '%{http_code}' -c "$T/p.txt" -d 'usuario=jmartinez&clave=Clave.2026' http://127.0.0.1:8100/ingresar); [ "$C" = 401 ] || fallo "el portal no debería poder verificar con el conector apagado (código $C)"
echo "el portal no puede verificar claves mientras el conector está apagado"
kill %1 %2; sleep 0.4

paso "Aplicaciones simuladas con el conector ENCENDIDO"
OBS_CONECTOR_ACTIVO=1 $N test/app-simulada.js 8101 "Solución Automatizada" secreto-solucion-prueba &
OBS_CONECTOR_ACTIVO=1 $N test/app-simulada.js 8102 "Catálogo de IA" secreto-catalogo-prueba & sleep 0.8
curl -s -o /dev/null -w '%{http_code}' -d 'usuario=jmartinez&clave=incorrecta' http://127.0.0.1:8100/ingresar | grep -q 401 || fallo "clave incorrecta aceptada"
echo "clave incorrecta rechazada"
curl -s -o /dev/null -w '%{http_code}' -c "$T/p.txt" -d 'usuario=jmartinez&clave=Clave.2026' http://127.0.0.1:8100/ingresar | grep -q 303 || fallo "ingreso al portal con la clave de la aplicación"
curl -s -b "$T/p.txt" http://127.0.0.1:8100/escritorio | grep -q "Julián" || fallo "escritorio del portal"
echo "ingreso al portal con el usuario y la clave de la Solución Automatizada"

paso "Abrir la aplicación desde el portal con la sesión ya iniciada"
DEST=$(curl -s -o /dev/null -w '%{redirect_url}' -b "$T/p.txt" http://127.0.0.1:8100/abrir/solucion)
echo "$DEST" | grep -q 'accion=sso&token=' || fallo "el portal no redirigió al conector"
curl -s -c "$T/app1.txt" -o /dev/null -w '%{http_code}\n' "$DEST" | grep -q 303 || fallo "el conector no abrió la sesión"
curl -s -b "$T/app1.txt" http://127.0.0.1:8101/ | grep -q "Sesión de: Julián" || fallo "la aplicación no reconoce la sesión abierta por el portal"
echo "la Solución Automatizada se abrió con la sesión de Julián iniciada, sin pedir clave"
curl -s -o /dev/null -w '%{http_code}' "$DEST" | grep -q 401 || fallo "un token reutilizado debería rechazarse"
echo "el token de un solo uso no puede reutilizarse"

paso "Vincular la segunda aplicación y abrirla"
curl -s -o /dev/null -w '%{redirect_url}\n' -b "$T/p.txt" http://127.0.0.1:8100/abrir/catalogo | grep -q '/vincular/catalogo' || fallo "sin vínculo debería pedir vinculación"
CSRF=$(curl -s -b "$T/p.txt" http://127.0.0.1:8100/vincular/catalogo | grep -o 'name="_csrf" value="[^"]*"' | head -1 | sed 's/.*value="//;s/"//')
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "usuario=jmartinez&clave=Clave.2026&_csrf=$CSRF" http://127.0.0.1:8100/vincular/catalogo | grep -q 303 || fallo "vinculación del catálogo"
DEST2=$(curl -s -o /dev/null -w '%{redirect_url}' -b "$T/p.txt" http://127.0.0.1:8100/abrir/catalogo)
curl -s -c "$T/app2.txt" -o /dev/null "$DEST2"; curl -s -b "$T/app2.txt" http://127.0.0.1:8102/ | grep -q "Sesión de: Julián" || fallo "sesión en el catálogo"
echo "el Catálogo de IA quedó vinculado y se abre con la sesión iniciada"

paso "Recolección de datos para el cuadro de mando"
$N src/cli.js recolectar > "$T/rec.json"; grep -q '"estado": "ok"' "$T/rec.json" || fallo "recolección"
grep -c '"conjunto"' "$T/rec.json" | grep -q 4 || fallo "se esperaban 4 conjuntos"
curl -s -b "$T/p.txt" http://127.0.0.1:8100/tablero | grep -q "Diagnósticos realizados" || fallo "tablero sin datos"
curl -s -b "$T/p.txt" http://127.0.0.1:8100/tablero | grep -q "Fichas del catálogo" || fallo "tablero sin datos del catálogo"
echo "cuatro conjuntos recolectados en solo lectura y visibles en el cuadro de mando"

paso "Administración"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" http://127.0.0.1:8100/admin | grep -q 403 || fallo "un usuario común no debe ver administración"
curl -s -o /dev/null -c "$T/adm.txt" -d 'usuario=jvergaras@unicartagena.edu.co&clave=Admin.2026' http://127.0.0.1:8100/ingresar
curl -s -b "$T/adm.txt" http://127.0.0.1:8100/admin | grep -q 'chip ok">Activo' || fallo "el administrador debería ver los conectores activos"
echo "el administrador ve el estado de los conectores y la auditoría"

echo; echo "TODAS LAS PRUEBAS PASARON"
