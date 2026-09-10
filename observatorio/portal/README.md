# Portal del Observatorio Nacional de Inteligencia Artificial

Aplicación web del portal con ingreso unificado y recolección de datos de las aplicaciones del proyecto IA para el Estado. Está escrita en Node.js 22 sin dependencias externas, usa una base de datos SQLite propia y se comunica con cada aplicación a través de un conector firmado que se describe en `../conectores/PROTOCOLO.md`.

## Qué hace en esta primera etapa

El usuario ingresa al portal con el usuario y la clave que ya tiene en la Solución Automatizada o en el Catálogo de IA. El portal verifica la clave en la aplicación correspondiente a través de su conector, crea la cuenta del portal vinculada a esa identidad y abre la sesión. Desde el menú Aplicativos, cada aplicación se abre en una pestaña con la sesión ya iniciada mediante un token firmado de un solo uso. La segunda aplicación se vincula la primera vez con sus propias credenciales y después se abre sin pedirlas. Un proceso programado pide a cada conector sus conjuntos de datos en solo lectura y los guarda en el portal para el cuadro de mando.

Las aplicaciones siguen funcionando de forma independiente, con su propio ingreso, con o sin el conector. El portal no escribe en sus bases de datos ni guarda claves.

## Requisitos

Node.js 22.5 o superior. Nada más. La base de datos SQLite se crea sola en la ruta configurada.

## Instalación

```bash
cd observatorio/portal
cp .env.example .env
# edite .env con la clave de sesión, las direcciones y los secretos de cada aplicación
npm start
```

El portal queda disponible en el puerto configurado. En producción debe colocarse detrás de un servidor web o un túnel que termine HTTPS, por ejemplo el mismo mecanismo con el que hoy se publican solucion.proyectoia.org y catalogoia.proyectoia.org, apuntando el subdominio del portal a este proceso.

## Configuración

Cada aplicación se declara con variables con el prefijo `APP_<CLAVE>_`. `CONECTOR` es la dirección interna con la que el portal verifica claves y recolecta datos, y `CONECTOR_PUBLICO` la dirección pública que recibe el navegador para abrir la sesión en la aplicación. En el mismo servidor la interna va por `host.docker.internal` y el tráfico nunca sale a internet. La clave es el identificador interno de la aplicación (por ejemplo SOLUCION o CATALOGO). El secreto debe ser el mismo que se configure en el conector de esa aplicación y debe tener al menos 64 caracteres aleatorios. Puede generarse con `node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"`.

La variable `ADMINISTRADORES` lista los correos que reciben el rol de administrador del portal al crear su cuenta. `MINUTOS_RECOLECCION` define cada cuánto se recolectan datos de las aplicaciones. Con 0 la recolección solo se ejecuta a mano desde la administración o con `npm run recolectar`.

## Pruebas

```bash
npm test
```

Levanta dos aplicaciones simuladas con el conector de referencia, primero apagado y luego encendido, y recorre el flujo completo. Ingreso con la clave de la aplicación, apertura con la sesión iniciada, rechazo de tokens reutilizados, vinculación de la segunda aplicación, recolección de datos y vista de administración.

## Estructura

| Archivo | Función |
|---|---|
| `src/server.js` | Servidor HTTP, rutas y protección de formularios |
| `src/auth.js` | Ingreso unificado, sesiones, cookies firmadas y control de intentos |
| `src/conector.js` | Cliente firmado de los conectores y emisión de tokens de apertura de sesión |
| `src/recolector.js` | Recolección programada de conjuntos de datos y resumen para el cuadro de mando |
| `src/db.js` | Esquema SQLite del portal y auditoría |
| `src/vistas.js` | Páginas HTML con la misma plantilla visual de la Solución Automatizada (cinta GOV.CO, cabecera MinTIC, menú Aplicativos, pie institucional) |
| `src/indicadores.js` | Marco de medición del Observatorio: diagnóstico por ámbitos, indicadores por dimensión, índice y niveles de madurez |
| `static/` | Hojas de estilo, logos, Bootstrap 5.3.3 y barra de accesibilidad servidos por el propio portal |
| `src/config.js` | Lectura de variables de entorno y del archivo .env |
| `test/app-simulada.js` | Aplicación existente simulada con conector, para pruebas |
| `test/e2e.sh` | Prueba de extremo a extremo con aplicaciones simuladas |
| `test/e2e-flask.sh` | Prueba de extremo a extremo con una Solución Automatizada real en Flask |

## Rutas

| Ruta | Acceso | Contenido |
|---|---|---|
| `/` | Pública | Portada del Observatorio con cifras generales |
| `/acerca` | Pública | Qué es el Observatorio, dimensiones, índice, niveles y modelo de seguimiento |
| `/ingresar` | Pública | Ingreso unificado con el usuario y la clave de cualquier aplicativo |
| `/aplicativos` | Con sesión | Tarjetas de los aplicativos, vinculación y apertura con sesión iniciada |
| `/tablero` | Con sesión | Cuadro de mando con los indicadores por dimensión y la evidencia recolectada |
| `/cuenta` | Con sesión | Identidades vinculadas y sesiones abiertas |
| `/admin` | Administradores | Estado de conectores, recolección manual, usuarios y auditoría |
| `/static/...` | Pública | Recursos estáticos |

## Cuestionarios y campañas

El módulo de cuestionarios permite a los administradores del portal diseñar instrumentos (pasos, secciones, preguntas de texto, opción única y múltiple, escalas, rúbricas de niveles, Sí/No, ranking, archivo adjunto, entidad pública con autocompletar, departamento y municipio, bloques condicionales), con o sin el bloque de políticas de privacidad y tratamiento de datos, publicarlos con un enlace público y aplicarlos por campañas de correo con enlace personal por destinatario, envío inmediato o programado y recordatorios a quienes no han respondido. Cada cuestionario tiene un panel de resultados con cifras, distribuciones, promedios por dimensión, filtros y exportación a hoja de cálculo, y sus promedios alimentan el cuadro de mando del Observatorio.

Los tres instrumentos que el proyecto ya aplicó (Información No Verificada, Autodiagnóstico Integrado y Diagnóstico de Infraestructura Computacional) se cargan la primera vez que arranca el portal como ejemplos protegidos, tomados de `src/ejemplos/*.json`, con su estilo, sus políticas y sus reglas de cálculo. Para adaptarlos se duplican.

Todos los enlaces (público y personales) y sus códigos QR (`/c/<clave>/qr.svg`, `/campanias/<id>/destinatarios/<id>/qr.svg`, hoja imprimible en `/campanias/<id>/qr`) se construyen en el momento con `URL_PUBLICA`: si el portal cambia de servidor o de dominio, basta actualizar esa variable y los QR y enlaces que se generen a partir de entonces apuntan al sitio nuevo (los correos ya enviados conservan la dirección con la que se enviaron). Los QR se generan en `src/qr.js`, sin servicios externos. Cada campaña pertenece a un periodo (corte), que separa las respuestas y se filtra en el cuadro de mando.

El correo saliente se configura con las variables `SMTP_*` y `CORREO_*` del archivo `.env` (ver `.env.example`). Sin ellas el portal funciona igual, pero las campañas quedan preparadas sin enviarse y los enlaces personales se copian a mano.

| Archivo | Función |
|---|---|
| `src/cuestionarios.js` | Definición, validación, cálculo de puntajes, página pública y persistencia |
| `src/campanias.js` | Campañas, destinatarios, plantillas de correo, envío inmediato, programado y recordatorios |
| `src/correo.js` | Cliente SMTP sin dependencias (TLS, STARTTLS, AUTH PLAIN y LOGIN) |
| `src/vistas_cuestionarios.js` | Lista, editor, resultados y campañas |
| `static/js/editor.js` | Editor visual de la definición |
| `static/js/cuestionario.js` y `static/css/cuestionario.css` | Página pública de diligenciamiento |
| `static/datos/` | Entidades públicas y municipios para el autocompletar |
| `test/e2e-cuestionarios.sh` | Prueba de extremo a extremo con un servidor SMTP simulado |

| Ruta | Acceso | Contenido |
|---|---|---|
| `/c/<clave>` | Pública | Diligenciamiento del cuestionario publicado |
| `/c/<clave>/t/<token>` | Pública | Diligenciamiento con enlace personal de campaña |
| `/cuestionarios` | Administradores | Lista, editor (`/nuevo`, `/<id>/editar`), resultados (`/<id>`), exportación (`/<id>/respuestas.csv`) |
| `/cuestionarios/<id>/campanias` y `/campanias/<id>` | Administradores | Campañas de aplicación y seguimiento de envíos |

## Reversa

Detener el proceso del portal devuelve todo al estado anterior. Las aplicaciones no dependen de él. Apagar la variable de activación del conector en una aplicación la desconecta del portal sin redesplegar nada.
