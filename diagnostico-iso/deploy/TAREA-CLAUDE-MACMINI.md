# Tarea para Claude Code en el Mac mini · integración de Diagnóstico ISO 9001 con el gestor y el portal

Contexto. La aplicación **Diagnóstico ISO 9001** (Node.js, sin dependencias) vive en este repositorio, carpeta
`diagnostico-iso/`, rama `claude/elegant-fermi-1ldlft`. Está instalada en `~/Servidor/apps/diagnosticoiso/diagnostico-iso`
(o en `~/apps/project-manager/diagnostico-iso` si aún no se movió), corre como agente launchd
`org.proyectoia.diagnosticoiso` en el puerto 3050 y se publica en https://diagnosticoiso.proyectoia.org por el túnel
`org.proyectoia.diagnosticoiso.tunel`. El gestor de proyectos (Python) está en `~/Servidor/apps/gestor`
(`servidor.py`, `auth.py`; login en `POST /api/login` con campos `usuario` y `clave`; sesión en `/api/sesion`).
El portal app.proyectoia.org es una página estática servida desde este servidor.

Objetivo. Dejar funcionando, sin intervención manual posterior, tres cosas:

## 1. Actualizar la aplicación
```bash
cd ~/Servidor/apps/diagnosticoiso/diagnostico-iso 2>/dev/null || cd ~/apps/project-manager/diagnostico-iso
bash deploy/instalar-macmini.sh
```
El instalador actualiza el código, conserva `.env`, base de datos y `cloudflared.yml`, y reinicia los servicios.

## 2. Sincronización automática de usuarios del gestor
La aplicación ya trae el mecanismo (ver `server/auth.js`, función `programarSincronizacion`). Solo hay que
indicarle la fuente en el `.env` de la aplicación. Preferir la opción a).

a) **Archivo de usuarios del gestor** (misma máquina, solo lectura). Localizar en `~/Servidor/apps/gestor`
   dónde persiste `auth.py` los usuarios (JSON o SQLite; revisar `AUTENTICACION`, `auth.py` y la carpeta `data/`).
   Escribir en el `.env` de la aplicación:
   ```
   GESTOR_USUARIOS_ARCHIVO=/ruta/absoluta/al/archivo
   GESTOR_USUARIOS_TABLA=usuarios      # solo si es SQLite y la tabla tiene otro nombre
   ```
   Si el archivo JSON tiene una estructura distinta de `[ {...}, ... ]`, `{ "usuarios": [...] }` o
   `{ "correo": {...}, ... }`, adaptar `leerUsuariosDeArchivo` en `server/auth.js` para devolver una lista de
   objetos con al menos `usuario` o `correo`, `nombre`, `rol` y opcionalmente `cargo` y `activo`.

b) Si no es viable leer el archivo, usar la API: verificar en `servidor.py` la ruta que lista usuarios para un
   administrador (buscar `ruta == "/api/usuarios"`), y escribir en el `.env`:
   ```
   GESTOR_USUARIOS_API=https://gestor.proyectoia.org/<ruta que lista usuarios>
   GESTOR_SERVICIO_USUARIO=<usuario administrador del gestor>
   GESTOR_SERVICIO_CLAVE=<su clave>
   ```

Después: `launchctl kickstart -k gui/$(id -u)/org.proyectoia.diagnosticoiso`, revisar `logs/salida.log` y
`logs/error.log` (debe aparecer `[sync] Usuarios del gestor sincronizados automáticamente`), y comprobar con
`curl -s http://127.0.0.1:3050/api/config` que responde. Validar creando un usuario de prueba en el gestor y
verificando que aparece en https://diagnosticoiso.proyectoia.org, menú Usuarios, en menos de un minuto (archivo)
o en el siguiente ciclo (API). Roles: los roles del gestor listados en `GESTOR_ADMIN_ROLES` entran como
administrador, los de `GESTOR_CONSULTOR_ROLES` como consultor y el resto como usuario; ajustar esas variables a
los nombres de rol reales del gestor.

## 3. Tarjeta en el portal app.proyectoia.org
```bash
python3 deploy/portal-agregar-tarjeta.py
```
Localiza el archivo del portal (busca "Observatorio de Riesgos IA" y "Gestor Proyecto"), duplica la tarjeta
"Gestor Proyecto" con el mismo formato y crea "Diagnóstico ISO 9001" con enlace a
https://diagnosticoiso.proyectoia.org/. Si no logra delimitar la tarjeta, hacerlo a mano copiando la de
"Gestor Proyecto" con título "Diagnóstico ISO 9001", descripción "Cuestionario de implementación ISO 9001:2015,
versiones, indicadores y brecha para la certificación." y un ícono de lista de verificación. Comprobar en el
navegador que aparece.

## Restricciones
- No modificar el gestor ni sus datos; la integración es de solo lectura sobre sus usuarios.
- No versionar `.env`, `cloudflared.yml` ni `data/` (ya están en `.gitignore`).
- Si se cambia código de la aplicación, ejecutar `npm test` y hacer commit en la rama `claude/elegant-fermi-1ldlft`
  con un mensaje descriptivo en español.
