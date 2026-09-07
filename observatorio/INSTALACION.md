# Guía de instalación y operación del portal del Observatorio

Versión 0.1. Septiembre de 2026. Dirigida al ingeniero de sistemas que instale o mantenga el portal.

## 1. Qué se instala y qué no se toca

El portal es un contenedor nuevo, independiente, que corre en el mismo servidor que las aplicaciones del proyecto y se publica en observatorioia.proyectoia.org a través del túnel existente. Las aplicaciones actuales no cambian ni un archivo. Para que el portal pueda verificar claves y abrir sesiones en ellas, cada aplicación recibe dos archivos nuevos montados desde fuera de su imagen, más un cambio en su comando de arranque dentro del compose. Con esos archivos y el interruptor apagado, la aplicación se comporta igual que antes. Retirarlos consiste en restaurar el comando de arranque original.

La Tabla 1 resume las piezas y su ubicación en el servidor.

| Pieza | Ubicación en el servidor | Se modifica algo existente |
|---|---|---|
| Portal (contenedor observatorio) | ~/Servidor/apps/observatorio | No, carpeta nueva |
| Ruta del túnel | ~/Servidor/rutas.conf | Se agrega una línea |
| Botón en la página principal | ~/Servidor/web/index.html | Se inserta un bloque, con copia de seguridad |
| Conector de la Solución Automatizada | ~/Servidor/apps/mintic1519/observatorio/ | No. Carpeta nueva montada por volumen. Cambia el comando en el compose |
| Conector del Catálogo de IA | ~/Servidor/apps/catalogoia/observatorio/ | No. Carpeta nueva montada por volumen. Cambia el comando en el compose |

Tabla 1. Componentes de la instalación. Fuente. Elaboración propia.

## 2. Requisitos

Docker con Compose (OrbStack en el Mac mini) y el túnel de cloudflared que ya publica las demás aplicaciones. Nada más. El portal no requiere Node ni Python instalados en el servidor porque corre en su contenedor.

## 2a. Instalación asistida con un solo script

La carpeta `despliegue` contiene `instalar.sh`, que ejecuta cada uno de los pasos siguientes con comprobaciones, copias de seguridad y reversa, de modo que el ingeniero de sistemas no necesite editar archivos a mano. Cada paso se puede repetir sin daño y se puede deshacer con la orden `revertir`. Los conectores no se agregan editando el compose de cada aplicación, sino con un archivo de superposición que se suma al original mediante una segunda opción `-f`, así que el compose de la aplicación queda intacto y retirar el conector consiste en volver a levantar el servicio sin esa superposición.

```bash
cd ~/Servidor/observatorio-portal/observatorio
bash despliegue/instalar.sh estado                 # qué hay instalado y qué responde
bash despliegue/instalar.sh portal                 # copia, crea .env con claves nuevas y levanta el contenedor
bash despliegue/instalar.sh tunel --recargar       # agrega la línea a rutas.conf y ejecuta scripts/tunel.sh
bash despliegue/instalar.sh boton                  # enlaza el Observatorio desde la página principal
bash despliegue/instalar.sh conector solucion      # conector de la Solución, apagado
bash despliegue/instalar.sh conector catalogo      # conector del Catálogo, apagado
bash despliegue/instalar.sh encender solucion      # cuando se autorice
bash despliegue/instalar.sh encender catalogo
```

Con `SIMULAR=1` delante de cualquier orden el script muestra lo que haría sin ejecutar docker ni escribir en el servidor, lo que sirve para revisar cada paso antes de aplicarlo. Las secciones siguientes describen a mano lo que el script hace, para quien prefiera hacerlo paso a paso o necesite entenderlo.

## 3. Instalación del portal (sin tocar las aplicaciones)

Copie la carpeta `observatorio/portal` de este repositorio a `~/Servidor/apps/observatorio` y ejecute lo siguiente desde esa carpeta.

```bash
cp .env.example .env
# Genere una clave de sesión y dos secretos de conector (uno por aplicación) y péguelos en .env
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))" 2>/dev/null || openssl rand -hex 48
docker compose -f docker-compose.servidor.yml up -d --build
curl -s http://127.0.0.1:8100/salud
```

La última orden debe responder con `{"ok":true,...}`. En este punto el portal está en el puerto 8100 del servidor, con su propia base de datos en un volumen, y todavía no puede verificar claves porque ningún conector está encendido. Eso es lo esperado.

Los valores de `.env` que hay que completar son `CLAVE_SESION`, `ADMINISTRADORES` (correos que serán administradores del portal), `APP_SOLUCION_SECRETO` y `APP_CATALOGO_SECRETO`. Las direcciones internas de los conectores ya vienen en el compose apuntando a los puertos 8010 y 8020 del servidor por `host.docker.internal`, de modo que el tráfico entre portal y aplicaciones no sale a internet. Las direcciones públicas, que son las que recibe el navegador del usuario para abrir la sesión en cada aplicación, también vienen en el compose y corresponden a los subdominios de cada una.

## 4. Publicar el portal en el túnel

El archivo `~/Servidor/rutas.conf` tiene un renglón por aplicación con tres campos separados por espacios: subdominio, puerto y protección. Agregue al final este renglón, que es el que corresponde al portal.

```
observatorioia 8100   publico
```

El puerto 8100 está libre (los ocupados llegan hasta 8080 y de 8020 a 8061). Después ejecute `scripts/tunel.sh` como hace con cualquier aplicación nueva. Cree el registro DNS del subdominio en Cloudflare si el script no lo hace. Verifique con el navegador que observatorioia.proyectoia.org muestra la pantalla de ingreso.

## 5. Botón en la página principal

La página principal ya tiene una tarjeta "Observatorio IA", pero es un botón sin destino que solo muestra el aviso "próximamente". Ejecute `portal-app-boton/agregar-boton.sh` de este repositorio: hace copia de seguridad de `~/Servidor/web/index.html` y sustituye ese botón por la tarjeta enlazada de `boton-observatorio.html`, que usa las clases propias de la página (`boton`, `icono`, `titulo-boton`, `desc-boton`, `pie-boton`) y conserva el mismo icono, la misma posición y el mismo retardo de aparición, de modo que la rejilla no cambia de aspecto. Si esa tarjeta ya no existiera, el script agrega la nueva al final de la rejilla de botones. No reinicia nada porque nginx sirve el archivo tal cual. Para deshacer, restaure la copia `.bak` que el script indica al terminar.

## 6. Conector de la Solución Automatizada (mintic1519)

Este conector está probado contra una réplica con la misma estructura de módulos de la aplicación (wsgi.app, web.app.csrf, src.models.user.User con bcrypt, Flask-Login y src.services.audit_service). Los pasos son los siguientes.

1. Cree la carpeta `~/Servidor/apps/mintic1519/observatorio/` y copie ahí `conectores/python/observatorio_conector.py` y `conectores/mintic1519/wsgi_observatorio.py`.
2. En `docker-compose.servidor.yml` del servicio web (mintic-web), agregue los dos volúmenes de solo lectura, las dos variables de entorno y cambie el comando, tal como se indica en el encabezado de `wsgi_observatorio.py`. Deje `OBS_CONECTOR_ACTIVO` en 0.
3. Reinicie solo ese servicio con `docker compose -f docker-compose.servidor.yml up -d web` (o el nombre que tenga el servicio). Compruebe que solucion.proyectoia.org responde igual que antes y que `curl -X POST http://127.0.0.1:8010/observatorio-conector` devuelve 404.
4. Cuando decida encender, ponga `OBS_CONECTOR_ACTIVO` en 1, vuelva a levantar el servicio y compruebe desde la administración del portal que el conector aparece como activo.

Si en cualquier momento algo falla, restaure `command: gunicorn wsgi:app ...` en el compose y levante el servicio. La aplicación vuelve al estado exacto anterior porque sus archivos nunca cambiaron.

## 7. Conector del Catálogo de IA (catalogoia)

El archivo `conectores/catalogoia/servidor_observatorio.py` ya está ajustado al código real del Catálogo (`app.py`, revisado el 6 de septiembre de 2026): objeto Flask `app`, base SQLite en `DATA_DIR/catalogo.db`, tabla `usuarios(id, username, password_hash, nombre, creado)`, claves verificadas con `check_password_hash` de werkzeug y sesión abierta igual que su propio ingreso (`session.clear()`, token CSRF nuevo, `user_id` y `username`). Como el `username` del Catálogo es el correo institucional y todos sus usuarios entran al panel, el conector los reporta con rol de administrador. Expone cinco conjuntos de solo lectura: fichas, herramientas, casos, usuarios y consultas.

Un detalle propio de esta aplicación: el Catálogo protege con un token de formulario todos los POST. El conector se exime únicamente en su propia ruta, envolviendo la comprobación ya registrada, sin modificar `app.py`. Las demás pantallas siguen protegidas igual que antes.

Los pasos son los siguientes.

1. Cree la carpeta `~/Servidor/apps/catalogoia/observatorio/` y copie ahí `conectores/python/observatorio_conector.py` y `conectores/catalogoia/servidor_observatorio.py`.
2. En `docker-compose.servidor.yml` del Catálogo, agregue a la lista de volúmenes del servicio `web` los dos montajes de solo lectura, agregue las dos variables de entorno y agregue el comando de arranque. Deje `OBS_CONECTOR_ACTIVO` en 0.

```yaml
    volumes:
      - ./observatorio/servidor_observatorio.py:/app/servidor_observatorio.py:ro
      - ./observatorio/observatorio_conector.py:/app/observatorio_conector.py:ro
    environment:
      OBS_CONECTOR_ACTIVO: "0"          # 1 para encender
      OBS_CONECTOR_SECRETO: ${OBS_CONECTOR_SECRETO_CATALOGO}
    command: ["python", "servidor_observatorio.py"]
```

3. Levante solo ese servicio con `docker compose -f docker-compose.servidor.yml up -d web`. Compruebe que catalogoia.proyectoia.org responde igual que antes, que su panel `/admin` sigue pidiendo clave y que `curl -X POST http://127.0.0.1:8020/observatorio-conector` devuelve 404.
4. Cuando decida encender, ponga `OBS_CONECTOR_ACTIVO` en 1, vuelva a levantar el servicio y compruebe desde la administración del portal que el conector aparece como activo.

El archivo de arranque reemplaza a `arranque.sh` y hace lo mismo que él: copia la semilla inicial si falta y sirve la aplicación con waitress en el puerto interno 8080, con los mismos parámetros de `servidor.py`. Para revertir, borre el `command:` del compose (la imagen vuelve a su arranque propio) y levante el servicio.

## 8. Comprobación completa

En el portal, ingrese con el correo y la clave que ya usa en la Solución Automatizada. Debe llegar a la página Aplicativos con la Solución marcada como vinculada. Pulse Abrir en la tarjeta de la Solución (o use el menú desplegable Aplicativos). Debe abrirse solucion.proyectoia.org con la sesión ya iniciada. Vuelva al portal, abra Administración y pulse Recolectar ahora. En el cuadro de mando deben aparecer entidades, evaluaciones, consolidados y usuarios.

## 9. Operación diaria

El portal recolecta datos cada hora por defecto (`MINUTOS_RECOLECCION` en `.env`). La base de datos vive en el volumen `observatorio_datos` y entra en las copias de seguridad como cualquier otro volumen del servidor. Los registros del contenedor se consultan con `docker logs observatorio`. La auditoría del portal (ingresos, aperturas de sesión, recolecciones, errores) está en la pantalla de Administración y en la tabla `auditoria` de la base.

Para actualizar el portal, reemplace la carpeta con la versión nueva y ejecute `docker compose -f docker-compose.servidor.yml up -d --build`. La base de datos se conserva porque está en el volumen. Para detenerlo por completo, `docker compose -f docker-compose.servidor.yml down`. Las aplicaciones no se ven afectadas en ningún caso.

## 10. Instalación en otro servidor

El portal solo necesita Docker. Copie la carpeta, configure `.env` con las direcciones de los conectores de ese servidor y levante el compose. Los conectores se instalan en cada aplicación con el mismo procedimiento de las secciones 6 y 7. Si las aplicaciones corren en otra máquina, cambie `host.docker.internal` por su dirección y use HTTPS entre servidores.

## 11. Mantenimiento por un ingeniero de sistemas

El código del portal son ocho archivos en `portal/src`, sin dependencias externas, cada uno con un propósito único descrito en `portal/README.md`. Las páginas HTML están en `vistas.js`. La lógica de ingreso está en `auth.js`. La comunicación con las aplicaciones está en `conector.js`. Agregar una tercera aplicación es declarar cinco variables `APP_<CLAVE>_` en `.env` e instalar su conector con el mismo archivo `observatorio_conector.py`. El protocolo completo del conector está en `conectores/PROTOCOLO.md`.

Las pruebas se ejecutan con `npm test` (aplicaciones simuladas en Node) y `bash test/e2e-flask.sh` (Solución simulada en Flask con la estructura real; necesita un Python con Flask, Flask-Login, Flask-WTF, Flask-SQLAlchemy y bcrypt, que el propio script busca e indica cómo preparar). Ambas levantan todo en puertos locales, recorren el flujo completo y apagan lo que levantaron.
