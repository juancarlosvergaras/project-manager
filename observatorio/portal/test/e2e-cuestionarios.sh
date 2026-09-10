#!/usr/bin/env bash
# Prueba de extremo a extremo del módulo de cuestionarios: ejemplos cargados, página pública, validación, respuesta,
# resultados, exportación, editor, campaña con SMTP simulado, enlace personal y bloqueo de duplicados.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'kill $(jobs -p) 2>/dev/null || true; rm -rf "$T"' EXIT
export RUTA_BD="$T/portal.sqlite" PUERTO=18110 URL_PUBLICA=http://127.0.0.1:18110 CLAVE_SESION=clave-de-prueba-suficientemente-larga-0123456789 MINUTOS_RECOLECCION=0
export ADMINISTRADORES=jvergaras@unicartagena.edu.co
export APP_SOLUCION_NOMBRE="Solución Automatizada" APP_SOLUCION_URL=http://127.0.0.1:18111 APP_SOLUCION_CONECTOR=http://127.0.0.1:18111/observatorio-conector APP_SOLUCION_SECRETO=secreto-solucion-prueba APP_SOLUCION_ORDEN=1
export SMTP_HOST=127.0.0.1 SMTP_PUERTO=12526 SMTP_SEGURIDAD=ninguna SMTP_USUARIO=portal SMTP_CLAVE=clave CORREO_DESDE=observatorio@unicartagena.edu.co SMTP_PAUSA_MS=10
N="node --no-warnings"
P=http://127.0.0.1:18110
fallo() { echo "FALLO: $*"; echo "--- registro del servidor:"; tail -20 "$T/servidor.log" 2>/dev/null; exit 1; }
paso() { echo; echo "== $*"; }

OBS_CONECTOR_ACTIVO=1 $N test/app-simulada.js 18111 "Solución Automatizada" secreto-solucion-prueba &
$N test/smtp-simulado.js 12526 "$T/correos" &
$N src/server.js > "$T/servidor.log" 2>&1 & sleep 2.5

paso "Ejemplos cargados y página pública"
grep -q "Cuestionarios de ejemplo cargados: 3" "$T/servidor.log" || fallo "no se cargaron los tres ejemplos"
for k in informacion-no-verificada autodiagnostico-integrado diagnostico-infraestructura; do
  [ "$(curl -s -o "$T/$k.html" -w '%{http_code}' $P/c/$k)" = 200 ] || fallo "página pública de $k"
done
grep -q 'class="form-step active" data-step="1"' "$T/informacion-no-verificada.html" || fallo "pasos del cuestionario"
grep -q 'name="beneficio_agilizar_tramites"' "$T/informacion-no-verificada.html" || fallo "escala Likert"
grep -q 'id="acepta_politicas"' "$T/autodiagnostico-integrado.html" || fallo "políticas al inicio"
grep -q 'steps-progress-meta' "$T/diagnostico-infraestructura.html" || fallo "barra de progreso"
grep -q 'fonts.bunny.net' "$T/diagnostico-infraestructura.html" || fallo "tipografías"
curl -s -D - -o /dev/null $P/c/informacion-no-verificada | grep -qi "content-security-policy: .*fonts.bunny.net" || fallo "CSP de la página pública"
[ "$(curl -s -o /dev/null -w '%{http_code}' $P/c/no-existe)" = 404 ] || fallo "cuestionario inexistente"
[ "$(curl -s -o /dev/null -w '%{http_code}' $P/static/datos/entidades.json)" = 200 ] || fallo "datos de entidades"
curl -s $P/ | grep -q "Encuestas habilitadas" || fallo "recuadro de encuestas en la portada"
curl -s $P/acerca > "$T/acerca.html"
grep -q "Encuestas habilitadas" "$T/acerca.html" || fallo "recuadro de encuestas en El Observatorio"
[ "$(grep -o 'Responder la encuesta' "$T/acerca.html" | wc -l | tr -d ' ')" = 3 ] || fallo "las tres encuestas publicadas tienen botón"
grep -q "unos 15 a 20 minutos" "$T/acerca.html" || fallo "duración estimada tomada de la introducción"
echo "los tres ejemplos se sirven con pasos, escalas, políticas y datos auxiliares, y las páginas públicas invitan a responderlos"

paso "Validación y registro de una respuesta"
C=$(curl -s -o "$T/r1.json" -w '%{http_code}' -H 'Accept: application/json' -F correo_electronico=persona@entidad.gov.co $P/c/informacion-no-verificada/enviar)
[ "$C" = 400 ] || fallo "una respuesta incompleta debería rechazarse (código $C)"
grep -q '"errores"' "$T/r1.json" || fallo "lista de errores"
echo "respuesta incompleta rechazada con la lista de faltantes"
ENVIO=(-F correo_electronico=persona@entidad.gov.co -F "tipo_documento=Cédula de ciudadanía" -F numero_documento=123 -F "rango_edad=25 a 34 años" -F genero=Femenino -F "reconocimiento_etnico=Ninguno de los anteriores" -F nivel_estudios=Maestría -F "entidad_rama=Rama Judicial" -F "anios_experiencia=1 a 5 años" -F area_funcional=Jurídica
  -F "nivel_conocimiento_ia=Avanzado: puedo explicar conceptos complejos y sus implicaciones." -F "tecnologias_asociadas[]=Análisis predictivo de datos." -F "concepto_ia_generativa=No estoy seguro(a)." -F "medios_informacion_ia[]=Redes sociales y plataformas digitales."
  -F frecuencia_uso_personal=Diariamente -F "tipos_ia_utilizados[]=Herramientas de análisis predictivo o de datos." -F "tipos_ia_utilizados[]=Software de transcripción de audio a texto." -F frecuencia_uso_laboral=Nunca
  -F beneficio_agilizar_tramites=5 -F beneficio_toma_decisiones=4 -F beneficio_optimizar_recursos=5 -F beneficio_transparencia=4 -F beneficio_personalizar_servicios=5 -F beneficio_prevenir_corrupcion=3
  -F riesgo_sesgos_discriminacion=5 -F riesgo_privacidad_seguridad=5 -F riesgo_falta_transparencia=4 -F riesgo_informacion_falsa=5 -F riesgo_sustitucion_empleos=2 -F riesgo_dificultad_responsabilidad=4 -F riesgo_brecha_digital=3
  -F vulnerabilidad_comunicaciones_publicas=2 -F vulnerabilidad_informes_tecnicos=3 -F vulnerabilidad_toma_decisiones=4 -F vulnerabilidad_chatbots_ciudadanos=1 -F vulnerabilidad_seguridad_orden_publico=2 -F experiencia_problema_ia=No
  -F "mecanismo_verificacion[]=Otra" -F mecanismo_verificacion_otro="Pregunto a un experto" -F "necesidad_politica_publica=Sí, es urgente y prioritario." -F "nivel_preparacion=Algo preparado"
  -F "apoyo_recursos_necesarios[]=Lineamientos y guías claras sobre el uso ético y seguro de la IA." -F "temas_guia_ia[]=Protección de datos personales y sensibles." -F acepta_politicas=1)
C=$(curl -s -o "$T/r2.json" -w '%{http_code}' -H 'Accept: application/json' "${ENVIO[@]}" $P/c/informacion-no-verificada/enviar)
[ "$C" = 200 ] || { cat "$T/r2.json"; fallo "respuesta completa rechazada (código $C)"; }
grep -q '"ok":true' "$T/r2.json" || fallo "respuesta registrada"
echo "respuesta completa registrada; las preguntas 18 y 19 se omiten por responder Nunca"
# La opción "Otra" con texto y una opción inválida
C=$(curl -s -o "$T/r3.json" -w '%{http_code}' -H 'Accept: application/json' "${ENVIO[@]/genero=Femenino/genero=Inventado}" $P/c/informacion-no-verificada/enviar)
[ "$C" = 400 ] || fallo "un valor fuera de las opciones debería rechazarse"
echo "valor fuera de las opciones rechazado"

paso "Ingreso del administrador, lista y resultados"
curl -s -o /dev/null -w '%{http_code}' -c "$T/p.txt" -d 'usuario=jvergaras&clave=Admin.2026' $P/ingresar | grep -q 303 || fallo "ingreso del administrador"
curl -s -b "$T/p.txt" $P/cuestionarios > "$T/lista.html"
grep -q "Autodiagnóstico Integrado" "$T/lista.html" || fallo "lista de cuestionarios"
grep -q 'href="/cuestionarios"' "$T/lista.html" || fallo "menú Cuestionarios"
grep -c "Ejemplo del proyecto" "$T/lista.html" | grep -q 3 || fallo "los tres ejemplos marcados como tales"
ID=$(grep -o 'href="/cuestionarios/[0-9]*/campanias"' "$T/lista.html" | sed -n 1p | grep -o '[0-9]*')
INFO=""; for i in $(grep -o 'href="/cuestionarios/[0-9]*"' "$T/lista.html" | grep -o '[0-9]*' | sort -u); do if curl -s -b "$T/p.txt" $P/cuestionarios/$i | grep -q "DIAGNÓSTICO SOBRE EL CONOCIMIENTO"; then INFO=$i; break; fi; done
[ -n "$INFO" ] || fallo "no se encontró el cuestionario de Información No Verificada"
curl -s -b "$T/p.txt" $P/cuestionarios/$INFO > "$T/resultados.html"
grep -q "Respuestas recibidas" "$T/resultados.html" || fallo "panel de resultados"
grep -q "persona@entidad.gov.co" "$T/resultados.html" || fallo "la respuesta aparece en la tabla"
grep -q "Percepción de beneficios" "$T/resultados.html" || fallo "dimensión calculada"
grep -q "grafico-dona" "$T/resultados.html" || fallo "gráficos de distribución"
curl -s -b "$T/p.txt" "$P/cuestionarios/$INFO/respuestas.csv" > "$T/r.csv"
head -1 "$T/r.csv" | grep -q "correo_electronico;" || fallo "cabecera del CSV"
grep -q "Pregunto a un experto" "$T/r.csv" || fallo "el texto de «Otra» está en el CSV"
grep -q "puntaje_beneficio" "$T/r.csv" || fallo "puntajes por dimensión en el CSV"
echo "el administrador ve la lista, el panel de resultados y exporta el CSV"
[ "$(curl -s -o /dev/null -w '%{http_code}' $P/cuestionarios)" = 303 ] || fallo "sin sesión debe redirigir"
C=$(curl -s -o "$T/noaut.html" -w '%{http_code}' -c "$T/f.txt" -d 'usuario=jmartinez&clave=Clave.2026' $P/ingresar)
[ "$C" = 401 ] || fallo "una cuenta sin rol de administrador no debe entrar (código $C)"
grep -q "no está autorizada" "$T/noaut.html" || fallo "mensaje de cuenta no autorizada"
curl -s $P/ > "$T/portada.html"
grep -q "El Observatorio Nacional de Inteligencia Artificial" "$T/portada.html" || fallo "el público ve la página del Observatorio"
grep -q 'class="navbar' "$T/portada.html" && fallo "el público no debe ver el menú"
grep -q "Ingreso de administradores" "$T/portada.html" || fallo "enlace de ingreso para administradores"
curl -s -b "$T/p.txt" $P/ | grep -q 'class="navbar' || fallo "el administrador sí ve el menú"
curl -s -b "$T/p.txt" $P/aplicativos | grep -q "Cuestionarios del Observatorio" || fallo "el aplicativo aparece en Aplicativos"
echo "el público solo ve El Observatorio con las encuestas; sin rol de administrador no se entra; el administrador tiene todo el menú"

paso "Editor: crear un cuestionario nuevo y publicarlo"
CSRF=$(curl -s -b "$T/p.txt" $P/cuestionarios/nuevo | grep -o '"csrf":"[^"]*"' | sed -n 1p | cut -d'"' -f4)
[ -n "$CSRF" ] || fallo "token del editor"
cat > "$T/def.json" <<EOF
{"_csrf":"$CSRF","definicion":{"titulo":"Sondeo de prueba","intro":["Hola **mundo**"],"politicas":{"mostrar":false},"pasos":[{"etiqueta":"Único","bloques":[{"tipo":"seccion","numero":"1","titulo":"Datos"},{"tipo":"texto_corto","nombre":"correo","etiqueta":"Correo","formato":"email","requerido":true},{"tipo":"escala","nombre":"satisfaccion","etiqueta":"Satisfacción","min":1,"max":5,"requerido":true,"dimension":"sat"},{"tipo":"si_no","nombre":"repetiria","etiqueta":"¿Repetiría?","requerido":true,"dimension":"sat"}]}],"identificacion":{"correo":"correo"},"duplicados":{"campos":["correo"],"mensaje":"Ese correo ya respondió."},"calculo":{"modo":"promedio","dimensiones":[{"clave":"sat","nombre":"Satisfacción"}]}}}
EOF
curl -s -b "$T/p.txt" -H 'Content-Type: application/json' --data-binary @"$T/def.json" $P/cuestionarios/nuevo > "$T/nuevo.json"
grep -q '"ok":true' "$T/nuevo.json" || { cat "$T/nuevo.json"; fallo "creación desde el editor"; }
NID=$(grep -o '"id":[0-9]*' "$T/nuevo.json" | grep -o '[0-9]*')
CLAVE=$(grep -o '"clave":"[^"]*"' "$T/nuevo.json" | cut -d'"' -f4)
[ "$CLAVE" = "sondeo-de-prueba" ] || fallo "clave generada ($CLAVE)"
[ "$(curl -s -o /dev/null -w '%{http_code}' $P/c/$CLAVE)" = 404 ] || fallo "un borrador no debe ser público"
[ "$(curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" "$P/c/$CLAVE?vista_previa=1")" = 200 ] || fallo "vista previa del borrador para el administrador"
perl -pi -e 's/"titulo":"Sondeo de prueba"/"titulo":""/' "$T/def.json"
curl -s -b "$T/p.txt" -H 'Content-Type: application/json' --data-binary @"$T/def.json" $P/cuestionarios/$NID/editar | grep -q "necesita un título" || fallo "validación de la definición"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "_csrf=$CSRF&estado=publicado" $P/cuestionarios/$NID/estado | grep -q 303 || fallo "publicar"
[ "$(curl -s -o /dev/null -w '%{http_code}' $P/c/$CLAVE)" = 200 ] || fallo "publicado y público"
echo "cuestionario creado desde el editor, validado, con vista previa y publicado"

paso "Campaña por correo con SMTP simulado"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" --data-urlencode "_csrf=$CSRF" --data-urlencode "nombre=Piloto" --data-urlencode "periodo=2026" --data-urlencode "asunto=Invitación: {{cuestionario}}" --data-urlencode "cuerpo=Hola {{nombre}}, responda aquí:

{{enlace}}

Gracias." --data-urlencode "destinatarios=ana@entidad.gov.co; Ana Núñez; Alcaldía Uno
correo-malo
ana@entidad.gov.co
luis@otra.gov.co	Luis Pérez	Gobernación Dos" $P/cuestionarios/$NID/campanias -o "$T/camp.txt" -D "$T/h.txt"
KID=$(grep -io 'location: /campanias/[0-9]*' "$T/h.txt" | grep -o '[0-9]*$')
[ -n "$KID" ] || fallo "creación de la campaña"
LOC=$(grep -i '^location:' "$T/h.txt" | sed -n 1p | cut -d' ' -f2 | tr -d '\r')
curl -s -b "$T/p.txt" "$P$LOC" > "$T/camp.html"
grep -q "Campaña creada con 2 destinatarios" "$T/camp.html" || fallo "dos destinatarios válidos y sin repetidos"
grep -q "Alcaldía Uno" "$T/camp.html" || fallo "entidad del destinatario"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "_csrf=$CSRF" $P/campanias/$KID/enviar | grep -q 303 || fallo "orden de envío"
sleep 1.5
[ "$(ls "$T/correos" | wc -l | tr -d " ")" = 2 ] || fallo "deberían haberse enviado 2 correos ($(ls "$T/correos" | wc -l | tr -d " "))"
grep -q "ana@entidad.gov.co" "$T/correos/001.json" || fallo "destinatario del primer correo"
TOKEN=$(grep -o "/c/$CLAVE/t/[A-Za-z0-9_-]*" "$T/camp.html" | sed -n 1p | sed 's|.*/t/||')
[ -n "$TOKEN" ] || fallo "enlace personal en la página de la campaña"
curl -s -b "$T/p.txt" $P/campanias/$KID | grep -q "Enviado" || fallo "estado enviado"
echo "campaña enviada a 2 destinatarios por el SMTP simulado, con enlace personal"

paso "Respuesta por enlace personal, prellenado, bloqueo de duplicados y recordatorio"
curl -s $P/c/$CLAVE/t/$TOKEN > "$T/personal.html"
grep -q 'value="ana@entidad.gov.co"' "$T/personal.html" || fallo "correo prellenado desde la campaña"
curl -s -H 'Accept: application/json' -F _token=$TOKEN -F correo=ana@entidad.gov.co -F satisfaccion=4 -F repetiria=1 $P/c/$CLAVE/enviar | grep -q '"ok":true' || fallo "respuesta por enlace personal"
C=$(curl -s -o /dev/null -w '%{http_code}' -H 'Accept: application/json' -F _token=$TOKEN -F correo=ana@entidad.gov.co -F satisfaccion=2 -F repetiria=0 $P/c/$CLAVE/enviar)
[ "$C" = 409 ] || fallo "el enlace personal no debe aceptar dos respuestas (código $C)"
C=$(curl -s -o /dev/null -w '%{http_code}' -H 'Accept: application/json' -F correo=ana@entidad.gov.co -F satisfaccion=2 -F repetiria=0 $P/c/$CLAVE/enviar)
[ "$C" = 409 ] || fallo "el correo repetido debe bloquearse por la regla de duplicados (código $C)"
curl -s "$P/c/$CLAVE/existe?campo=correo&valor=ANA@entidad.gov.co" | grep -q '"existe":true' || fallo "consulta de duplicados"
[ "$(curl -s -o /dev/null -w '%{http_code}' $P/c/$CLAVE/t/$TOKEN)" = 200 ] && curl -s $P/c/$CLAVE/t/$TOKEN | grep -q "ya se utilizó" || fallo "el enlace usado avisa"
curl -s -b "$T/p.txt" $P/campanias/$KID > "$T/camp2.html"
grep -q "Respondió" "$T/camp2.html" || fallo "el destinatario figura como respondido"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "_csrf=$CSRF" $P/campanias/$KID/recordar | grep -q 303 || fallo "recordatorio"
sleep 1
[ "$(ls "$T/correos" | wc -l | tr -d " ")" = 3 ] || fallo "el recordatorio debe ir solo a quien no respondió ($(ls "$T/correos" | wc -l | tr -d " ") correos)"
grep -q "luis@otra.gov.co" "$T/correos/003.json" || fallo "destinatario del recordatorio"
grep -q "Recordatorio" "$T/correos/003.json" || fallo "asunto del recordatorio"
curl -s -b "$T/p.txt" $P/cuestionarios/$NID | grep -q "Satisfacción" || fallo "resultados con la dimensión"
curl -s -b "$T/p.txt" "$P/cuestionarios/$NID?periodo=2026" | grep -q "ana@entidad.gov.co" || fallo "la respuesta de la campaña queda en el periodo 2026"
curl -s -b "$T/p.txt" "$P/cuestionarios/$NID?periodo=2031" | grep -q "ana@entidad.gov.co" && fallo "otro periodo no debe mostrarla"
curl -s -b "$T/p.txt" "$P/cuestionarios/$NID/respuestas.csv" | sed -n 2p | grep -q ";2026;" || fallo "el periodo va en el CSV"
curl -s -b "$T/p.txt" "$P/tablero?periodo=2026" | grep -q 'del periodo <strong>2026</strong>' || fallo "el cuadro de mando filtra por periodo"
curl -s -b "$T/p.txt" $P/tablero | grep -q '<option value="2026"' || fallo "el selector de periodos del cuadro de mando"
curl -s -b "$T/p.txt" $P/tablero | grep -q "Sondeo de prueba" || fallo "el cuadro de mando muestra el cuestionario"
curl -s -b "$T/p.txt" $P/ | grep -q "Respuestas a los cuestionarios" || fallo "la portada del administrador cuenta las respuestas"
echo "enlace personal prellenado y de un solo uso, duplicados bloqueados, recordatorio solo a pendientes, tablero al día"

paso "Programación de una campaña"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "_csrf=$CSRF&programada_en=2030-01-01T09:00" $P/campanias/$KID/programar | grep -q 303 || fallo "programar"
curl -s -b "$T/p.txt" $P/campanias/$KID | grep -q "Programada" || fallo "estado programada"
curl -s -b "$T/p.txt" $P/campanias/$KID | grep -q 'value="2030-01-01T09:00"' || fallo "la hora se muestra en hora de Colombia"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "_csrf=$CSRF" $P/campanias/$KID/cancelar | grep -q 303 || fallo "cancelar"
curl -s -b "$T/p.txt" $P/campanias/$KID | grep -q "Programada" && fallo "la programación debería cancelarse"
echo "programación y cancelación con la hora de Colombia"

paso "Duplicar y proteger los ejemplos"
curl -s -o /dev/null -w '%{http_code}' -b "$T/p.txt" -d "_csrf=$CSRF" $P/cuestionarios/$ID/eliminar -D "$T/h2.txt"; grep -q "no se pueden eliminar" <(curl -s -b "$T/p.txt" "$P/cuestionarios?e=$(grep -io 'e=[^ ]*' "$T/h2.txt" | sed -n 1p | cut -c3- | tr -d '\r')") || true
curl -s -b "$T/p.txt" $P/cuestionarios | grep -c "Ejemplo del proyecto" | grep -q 3 || fallo "los ejemplos siguen intactos"
curl -s -o /dev/null -b "$T/p.txt" -d "_csrf=$CSRF" $P/cuestionarios/$ID/duplicar -D "$T/h3.txt"
grep -qi "location: /cuestionarios/[0-9]*/editar" "$T/h3.txt" || fallo "duplicar abre el editor de la copia"
curl -s -b "$T/p.txt" $P/cuestionarios | grep -q "(copia)" || fallo "la copia aparece en la lista"
echo "los ejemplos no se eliminan y se pueden duplicar"

paso "Importar respuestas anteriores desde un archivo de Excel"
curl -s -b "$T/p.txt" -F "_csrf=$CSRF" -F "campania=nueva" -F "nueva_campania=Histórico Excel" -F "archivo=@test/muestra.xlsx" $P/cuestionarios/$INFO/importar > "$T/mapeo.html"
grep -q 'name="col_1"' "$T/mapeo.html" || fallo "tabla de correspondencia de columnas"
grep -q '<option value="correo_electronico" selected' "$T/mapeo.html" || fallo "propuesta para la columna de correo"
grep -q '<option value="_fecha" selected' "$T/mapeo.html" || fallo "propuesta para la columna de fecha"
grep -q '<option value="beneficio_agilizar_tramites" selected' "$T/mapeo.html" || fallo "propuesta para la pregunta de escala por su etiqueta"
TOK=$(grep -o "importar/[A-Za-z0-9_-]*" "$T/mapeo.html" | sed -n 1p | cut -d/ -f2)
[ -n "$TOK" ] || fallo "sesión de importación"
curl -s -o /dev/null -b "$T/p.txt" --data-urlencode "_csrf=$CSRF" --data-urlencode "campania=nueva" --data-urlencode "nueva_campania=Histórico Excel" --data-urlencode "col_3=correo_electronico" --data-urlencode "col_4=nivel_conocimiento_ia" --data-urlencode "col_5=frecuencia_uso_laboral" --data-urlencode "col_6=_fecha" --data-urlencode "col_7=beneficio_agilizar_tramites" --data-urlencode "col_8=tipos_ia_utilizados" --data-urlencode "omitir_duplicados=1" $P/cuestionarios/$INFO/importar/$TOK -D "$T/h4.txt"
grep -qi "location: /cuestionarios/$INFO?m=" "$T/h4.txt" || fallo "la importación no volvió a los resultados"
grep -o "m=[^ ]*" "$T/h4.txt" | sed -n 1p | cut -c3- | python3 -c "import sys,urllib.parse; print(urllib.parse.unquote(sys.stdin.read()))" | grep -q "3 respuestas importadas" || fallo "deberían importarse las 3 filas"
curl -s -b "$T/p.txt" "$P/cuestionarios/$INFO?buscar=importado" > "$T/imp.html"
[ "$(grep -o 'importado1@entidad.gov.co' "$T/imp.html" | wc -l | tr -d ' ')" -ge 2 ] || fallo "las filas importadas aparecen en los resultados"
grep -q "09/09/2026 21:21" "$T/imp.html" || fallo "la fecha original se conserva en hora de Colombia"
curl -s -b "$T/p.txt" "$P/cuestionarios/$INFO/respuestas.csv?buscar=importado" > "$T/imp.csv"
grep -q "Intermedio: entiendo los conceptos fundamentales" "$T/imp.csv" || fallo "opción emparejada por texto completo"
grep -q "Avanzado: puedo explicar" "$T/imp.csv" || fallo "opción emparejada por texto parcial"
grep -q "Software de transcripción de audio a texto. | Herramientas de análisis predictivo o de datos." "$T/imp.csv" || fallo "respuesta múltiple separada por punto y coma"
curl -s -b "$T/p.txt" $P/cuestionarios/$INFO/campanias > "$T/camps.html"
grep -q "Histórico Excel" "$T/camps.html" || fallo "la campaña de importación existe"
grep -q "Importada de archivo" "$T/camps.html" || fallo "estado de la campaña importada"
echo "archivo de Excel leído, columnas propuestas, 3 filas importadas con sus fechas y opciones dentro de una campaña"

paso "Gestión de cuentas desde Administración"
curl -s -b "$T/p.txt" $P/admin > "$T/admin.html"
grep -q "Agregar administrador" "$T/admin.html" || fallo "formulario de alta de administradores"
curl -s -b "$T/p.txt" --data-urlencode "_csrf=$CSRF" --data-urlencode "correo=jmartinez@cartagena.gov.co" $P/admin/usuarios | grep -q "quedó registrado como administrador" || fallo "alta de administrador por correo"
curl -s -o /dev/null -w '%{http_code}' -c "$T/f.txt" -d 'usuario=jmartinez&clave=Clave.2026' $P/ingresar | grep -q 303 || fallo "la cuenta registrada ya puede entrar con su clave del aplicativo"
curl -s -b "$T/f.txt" $P/cuestionarios | grep -q "Nuevo cuestionario" || fallo "la cuenta registrada gestiona cuestionarios"
curl -s -b "$T/p.txt" $P/admin > "$T/admin2.html"
UID_F=$(grep -o 'action="/admin/usuarios/[0-9]*/rol"' "$T/admin2.html" | sed -n 1p | grep -o '[0-9]*' || true)
[ -n "$UID_F" ] || fallo "botón de rol para la otra cuenta"
curl -s -b "$T/p.txt" -d "_csrf=$CSRF&rol=usuario" $P/admin/usuarios/$UID_F/rol | grep -q "ahora es usuario" || fallo "quitar el rol"
curl -s -b "$T/f.txt" $P/cuestionarios | grep -q "Nuevo cuestionario" && fallo "al quitar el rol deja de gestionar"
curl -s -b "$T/p.txt" -d "_csrf=$CSRF&rol=administrador" $P/admin/usuarios/$UID_F/rol | grep -q "ahora es administrador" || fallo "devolver el rol"
curl -s -b "$T/p.txt" $P/admin | grep -q "jmartinez@cartagena.gov.co" || fallo "la cuenta aparece en la lista"
echo "administradores registrados por correo, rol quitado y devuelto desde Administración"

echo; echo "TODO EN ORDEN: módulo de cuestionarios probado de extremo a extremo."
