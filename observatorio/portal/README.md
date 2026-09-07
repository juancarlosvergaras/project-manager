# Portal del Observatorio Nacional de Inteligencia Artificial

Aplicación web del portal con ingreso unificado y recolección de datos de las aplicaciones del proyecto IA para el Estado. Está escrita en Node.js 22 sin dependencias externas, usa una base de datos SQLite propia y se comunica con cada aplicación a través de un conector firmado que se describe en `../conectores/PROTOCOLO.md`.

## Qué hace en esta primera etapa

El usuario ingresa al portal con el usuario y la clave que ya tiene en la Solución Automatizada o en el Catálogo de IA. El portal verifica la clave en la aplicación correspondiente a través de su conector, crea la cuenta del portal vinculada a esa identidad y abre la sesión. Desde el escritorio, cada aplicación se abre en una pestaña con la sesión ya iniciada mediante un token firmado de un solo uso. La segunda aplicación se vincula la primera vez con sus propias credenciales y después se abre sin pedirlas. Un proceso programado pide a cada conector sus conjuntos de datos en solo lectura y los guarda en el portal para el cuadro de mando.

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

Cada aplicación se declara con cinco variables con el prefijo `APP_<CLAVE>_`. La clave es el identificador interno de la aplicación (por ejemplo SOLUCION o CATALOGO). El secreto debe ser el mismo que se configure en el conector de esa aplicación y debe tener al menos 64 caracteres aleatorios. Puede generarse con `node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"`.

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
| `src/vistas.js` | Páginas HTML |
| `src/config.js` | Lectura de variables de entorno y del archivo .env |
| `test/app-simulada.js` | Aplicación existente simulada con conector, para pruebas |
| `test/e2e.sh` | Prueba de extremo a extremo |

## Reversa

Detener el proceso del portal devuelve todo al estado anterior. Las aplicaciones no dependen de él. Apagar la variable de activación del conector en una aplicación la desconecta del portal sin redesplegar nada.
