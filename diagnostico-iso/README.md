# Diagnóstico ISO 9001 · diagnosticoiso.proyectoia.org

Herramienta en línea para aplicar, versionar y analizar el diagnóstico de implementación de la norma ISO 9001:2015 con su Enmienda 1:2024 en cualquier organización. Está diseñada para diligenciarse desde el teléfono móvil, se integra con el sistema de usuarios de gestor.proyectoia.org y se enlaza desde app.proyectoia.org.

## Funcionalidades

- **Organizaciones**. Creación y administración de organizaciones (nombre, sigla, NIT, sector, ciudad, contacto).
- **Asignación de organizaciones a usuarios**. Desde la pantalla de Usuarios se asignan a cada usuario una o varias de las organizaciones creadas mediante selección múltiple con filtro, con rol de editor o lector por organización, al estilo de la asignación de proyectos del gestor. También es posible asignar un usuario desde la propia organización.
- **Cuestionario**. Instrumento de 98 preguntas propias de aplicación, organizadas por capítulo (4 a 10) y numeral de la norma, con responsable sugerido de la evidencia.
- **Escala de valoración**. Cumple (100 %), Cumple parcialmente (50 %), No cumple (0 %) y No aplica (excluida del cálculo). Cada respuesta admite evidencia, observaciones y responsable.
- **Cuestionario editable**. El administrador agrega, edita, retira y restaura preguntas. Las versiones cerradas conservan las preguntas con las que se evaluaron; las abiertas y las nuevas usan el cuestionario vigente.
- **Tablero e informes**. Tablero visual con medidor de cumplimiento, distribución de respuestas, semáforo por capítulo, evolución entre versiones y requisitos más urgentes, e informe ejecutivo imprimible a PDF con resumen, comparación con la versión anterior, cumplimiento por numeral y plan de cierre de brechas.
- **Versiones e histórico**. Cada aplicación del cuestionario es una versión numerada de la organización. Una versión se cierra para congelarla y una nueva puede partir en blanco o heredar de una anterior (con o sin valoraciones). El histórico muestra la evolución del cumplimiento por versión y permite comparar dos versiones ítem a ítem.
- **Indicadores**. Cumplimiento global, brecha para alcanzar ISO 9001, nivel de madurez, capítulo crítico, distribución de valoraciones, cumplimiento por capítulo y por numeral, lista priorizada de requisitos por cerrar y carga por responsable. Exportación a CSV.
- **Impresión**. Formato en blanco (sin sesión) y formato diligenciado con filtro de versión, ambos optimizados para A4 horizontal.
- **Caso precargado**. Diagnóstico documental del Hospital Universitario del Caribe (98 respuestas, versión 1 cerrada), tomado del instrumento en Excel aportado. Las categorías originales (Evidencia parcial, Sin evidencia aportada, Brecha documental, Antecedente por verificar) se conservan en cada respuesta como estado de origen; las tres últimas se valoran como No cumple.
- **Aplicación instalable**. Manifiesto PWA para agregarla a la pantalla de inicio del teléfono.

## Arquitectura

| Capa | Tecnología |
|---|---|
| Servidor | Node.js 22.13 o superior, sin dependencias externas (`node:http`, `node:sqlite`, `node:crypto`) |
| Base de datos | SQLite en un archivo (WAL), esquema y datos semilla creados automáticamente al arrancar |
| Interfaz | HTML, CSS y JavaScript sin framework ni paso de compilación, diseño móvil primero |
| Autenticación | Sesiones propias en cookie firmada, con ingreso por gestor.proyectoia.org (SSO) o usuarios locales |

Estructura del proyecto:

```
diagnostico-iso/
  server/
    index.js      servidor HTTP, archivos estáticos y flujo SSO
    routes.js     API REST
    auth.js       sesiones, usuarios locales e integración con el gestor
    db.js         esquema SQLite, escala de valoración y carga de datos semilla
    scoring.js    indicadores, brecha, niveles de madurez y comparación de versiones
    seed/         instrumento (98 preguntas) y caso del Hospital Universitario del Caribe
  public/         interfaz (index.html, app.js, styles.css, manifest, ícono)
  integracion/    fragmento HTML del botón para app.proyectoia.org
  scripts/        importador de diagnósticos desde Excel
  deploy/         configuración de nginx y unidad de systemd
  test/           pruebas unitarias e integración (node --test)
```

## Puesta en marcha local

```bash
cd diagnostico-iso
npm run dev            # http://localhost:3010 en modo local
```

Usuario inicial: `admin@proyectoia.org` con contraseña `admin1234` (se crea solo si no hay usuarios; cámbiela en Mi perfil o defina `ADMIN_EMAIL` y `ADMIN_PASSWORD`).

Pruebas:

```bash
npm test
```

## Despliegue en diagnosticoiso.proyectoia.org

### Instalación rápida en un Mac (por ejemplo el Mac mini que aloja app y gestor)

Desde una terminal o una sesión SSH en el Mac:

```bash
curl -fsSL https://raw.githubusercontent.com/juancarlosvergaras/project-manager/main/diagnostico-iso/deploy/instalar-macmini.sh | bash
```

El script instala Node.js 22 si falta, clona o actualiza el repositorio en `~/Servidor/apps/diagnosticoiso` (si existía una instalación previa en `~/apps/project-manager` la mueve con su base de datos), crea el `.env` con un secreto y una contraseña de administrador generados, registra un servicio launchd que mantiene la aplicación activa en el puerto 3050 y muestra las instrucciones para publicar el subdominio en el túnel de Cloudflare ya existente. Ejecutarlo de nuevo actualiza a la última versión sin tocar la base de datos ni el `.env`. Variables opcionales: `RAMA`, `PUERTO` y `DESTINO`.

Para publicar el subdominio con un túnel de Cloudflare propio de la aplicación (mismo esquema que las demás apps del Mac, con su `cloudflared.yml` en la carpeta):

```bash
cd ~/Servidor/apps/diagnosticoiso/diagnostico-iso && bash deploy/tunel.sh
```

El script crea el túnel `diagnosticoiso` si no existe, escribe `cloudflared.yml` con el ID y las credenciales, valida la configuración, crea el registro DNS, deja cloudflared corriendo como agente launchd y comprueba que el dominio responde. Alternativa para agregar el hostname al túnel global de `/etc/cloudflared/config.yml`: `sudo bash deploy/publicar-tunel.sh`.

### Instalación manual en Linux

1. Copie la carpeta al servidor (por ejemplo `/opt/diagnostico-iso`) y cree `.env` a partir de `.env.example`. Defina como mínimo `SESSION_SECRET`, `BASE_URL`, `DB_PATH` y las variables `GESTOR_*`.
2. Opción A, systemd: copie `deploy/diagnostico-iso.service` a `/etc/systemd/system/`, ajuste usuario y rutas y ejecute `systemctl enable --now diagnostico-iso`.
3. Opción B, Docker: `docker compose up -d --build` (la base de datos queda en el volumen `diagnostico-data`).
4. Publique el subdominio con nginx usando `deploy/nginx.diagnosticoiso.conf` y emita el certificado con certbot. La cabecera `X-Forwarded-Proto https` es necesaria para que la cookie de sesión se marque como segura.
5. Registro DNS: `diagnosticoiso.proyectoia.org` apuntando al servidor.

Copia de seguridad: basta con copiar el archivo SQLite indicado en `DB_PATH` (con sus archivos `-wal` y `-shm` si existen).

## Integración con el sistema de usuarios de gestor.proyectoia.org

La herramienta no almacena contraseñas de los usuarios del gestor. Los crea localmente en su primer ingreso y sincroniza nombre y rol en cada acceso. Hay dos mecanismos, configurables por variables de entorno.

### Mecanismo 1 (activo por defecto): validación delegada de credenciales

El usuario escribe en el formulario de esta herramienta el mismo correo y contraseña del gestor. La herramienta envía las credenciales a `GESTOR_LOGIN_API` (por defecto `https://gestor.proyectoia.org/api/login`), y si el gestor las acepta consulta `GESTOR_SESION_API` (`/api/sesion`) con la cookie devuelta para obtener nombre y rol. No requiere cambios en el gestor. Los campos se envían con varios alias (`email`, `correo`, `usuario`, `password`, `clave`, `contrasena`); si el gestor exige nombres concretos se fijan con `GESTOR_LOGIN_CAMPOS=correo,clave`. Si el correo no existe en el gestor, se intenta con los usuarios locales de la herramienta.

### Mecanismo 2 (opcional): ingreso único por token

Flujo:

1. El usuario pulsa "Ingresar con Gestor ProyectoIA". La herramienta redirige a `GESTOR_LOGIN_URL` enviando la URL de retorno en el parámetro `GESTOR_REDIRECT_PARAM` (por defecto `redirect_uri`).
2. El gestor autentica al usuario y lo devuelve a `https://diagnosticoiso.proyectoia.org/auth/gestor/callback?token=…` (el nombre del parámetro se define en `GESTOR_TOKEN_PARAM`).
3. La herramienta valida el token con una de estas opciones:
   - `GESTOR_USERINFO_URL`: petición GET con `Authorization: Bearer <token>` que debe responder JSON con los campos `id` (o `sub`), `email`, `nombre` (o `name`) y `rol` (o `role` o `roles`). Esta es la opción recomendada porque el gestor conserva el control total de la validez de las sesiones.
   - `GESTOR_JWT_SECRET` (HS256) o `GESTOR_JWT_PUBLIC_KEY` (RS256): verificación local del JWT, con comprobación opcional de `iss` y `aud`.
   - `GESTOR_SESSION_COOKIE` junto con `GESTOR_USERINFO_URL`: si el gestor deja una cookie de sesión en el dominio `.proyectoia.org`, la herramienta la reenvía al gestor para identificar al usuario sin redirección.
4. Los roles del gestor listados en `GESTOR_ADMIN_ROLES` se traducen a administrador y los de `GESTOR_CONSULTOR_ROLES` a consultor. Cualquier otro rol ingresa como usuario y solo ve las organizaciones que se le asignen.

Alternativa por API: `POST /api/auth/gestor/token` con `{ "token": "…" }` canjea un token del gestor por una sesión. La interfaz lo hace automáticamente cuando se abre `https://diagnosticoiso.proyectoia.org/?token=…`, lo que permite que app.proyectoia.org enlace directamente sin pedir credenciales de nuevo.

`AUTH_MODE=gestor` desactiva el ingreso con usuarios locales, `AUTH_MODE=local` desactiva el gestor y `AUTH_MODE=mixto` (predeterminado) habilita ambos.

## Botón en app.proyectoia.org

La página principal es `~/Servidor/web/index.html` en el servidor (servida por nginx). El script `deploy/agregar-boton-portal.sh` inserta la tarjeta `deploy/boton-diagnostico.html` al final de la rejilla de botones con las clases propias de la página, con copia de seguridad, siguiendo el mismo patrón del botón del Observatorio:

```bash
bash deploy/agregar-boton-portal.sh
```

`integracion/boton-app-proyectoia.html` conserva un fragmento autónomo (con estilos propios) para cualquier otra página.

## Roles y permisos

El rol es global por usuario y el alcance lo dan las organizaciones asignadas (una o varias). Los administradores acceden a todas.

| Rol | Alcance |
|---|---|
| Administrador | Organizaciones, usuarios y asignaciones, cuestionario (agregar, editar y retirar preguntas), versiones, diligenciamiento, indicadores, tablero e informes de todas las organizaciones |
| Editor | En sus organizaciones: tablero, indicadores, históricos, comparaciones e informes; crea, cierra, reabre y elimina versiones; diligencia el cuestionario. No modifica el cuestionario |
| Auditor | En sus organizaciones: ve la versión en diligenciamiento y la alimenta con valoraciones, evidencias, observaciones y responsables |
| Usuario | En sus organizaciones: tablero de resultados, informes y exportación |

Los usuarios del gestor reciben el rol según `GESTOR_ADMIN_ROLES`, `GESTOR_EDITOR_ROLES` y `GESTOR_AUDITOR_ROLES` (el resto entra como usuario). Si el administrador cambia el rol de un usuario en esta herramienta, ese rol se conserva aunque el gestor lo sincronice.

## API principal

| Método y ruta | Descripción |
|---|---|
| `GET /api/config` | Modos de autenticación, escala de valoración y niveles de madurez |
| `POST /api/auth/local/login`, `POST /api/auth/logout` | Sesión local |
| `GET /api/organizaciones`, `POST /api/organizaciones`, `PUT /api/organizaciones/:id` | Organizaciones |
| `POST /api/organizaciones/:id/miembros`, `DELETE …/miembros/:usuarioId` | Asignación de un usuario desde la organización |
| `POST /api/instrumentos/:id/items`, `PUT …/items/:itemId`, `DELETE …/items/:itemId`, `POST …/items/:itemId/restaurar` | Edición del cuestionario (administrador) |
| `GET /api/usuarios/:id/organizaciones`, `PUT /api/usuarios/:id/organizaciones` | Organizaciones asignadas a un usuario; el PUT recibe `{ organizaciones: [{ id, rol }] }` y reemplaza la asignación |
| `POST /api/organizaciones/:id/diagnosticos` | Nueva versión (opcional `desde_version_id` y `modo_copia`) |
| `GET /api/organizaciones/:id/historico` | Serie histórica de cumplimiento por versión |
| `GET /api/diagnosticos/:id` | Versión con preguntas y respuestas |
| `PUT /api/diagnosticos/:id/respuestas/:itemId` | Guarda una respuesta (autoguardado) |
| `POST /api/diagnosticos/:id/cerrar`, `…/reabrir`, `DELETE /api/diagnosticos/:id` | Ciclo de vida de la versión |
| `GET /api/diagnosticos/:id/indicadores` | Indicadores y brecha |
| `GET /api/diagnosticos/:id/comparar/:otroId` | Comparación entre versiones |
| `GET /api/diagnosticos/:id/export.csv` | Exportación |
| `GET /api/instrumentos/:clave/items` | Instrumento (público, para el formato en blanco) |

## Método de cálculo

El cumplimiento global es el promedio de los pesos de las preguntas aplicables (Cumple 1, Cumple parcialmente 0,5, No cumple 0, Sin valorar 0). Las preguntas marcadas No aplica salen del denominador. La brecha es el complemento a 100. Los niveles de madurez son Inicial (menos de 25 %), Básico (25 a 49,9 %), En desarrollo (50 a 74,9 %), Avanzado (75 a 89,9 %) y Listo para certificación (90 % o más). La lista de brecha prioriza como alta las preguntas con No cumple o sin valorar y como media las de Cumple parcialmente.

## Importar un diagnóstico desde Excel

```bash
pip install openpyxl requests
python3 scripts/importar-excel.py Instrumento.xlsx --api https://diagnosticoiso.proyectoia.org \
  --email admin@proyectoia.org --password '…' --organizacion "Nombre" --sigla SIG
```

El archivo debe conservar los encabezados del instrumento (ID, Capítulo, Numeral ISO, Pregunta, Estado, Evidencia, Observaciones, Responsable). Los estados textuales se traducen a la escala de cuatro valores.
