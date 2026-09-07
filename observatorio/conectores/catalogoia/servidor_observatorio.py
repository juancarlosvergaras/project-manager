"""
Punto de entrada de la aplicacion Catalogo de IA (catalogoia) con el conector del Observatorio montado.

No modifica ningun archivo de la aplicacion ni el esquema de su base de datos. Reemplaza a `arranque.sh`:
copia la semilla inicial igual que aquel, importa la aplicacion Flask ya construida (`app.py`), le registra
el conector como blueprint y la sirve con waitress en el mismo puerto interno, con los mismos parametros
que `servidor.py`. Con OBS_CONECTOR_ACTIVO en 0 el conector responde 404 y el Catalogo se comporta
exactamente igual que antes.

Ajustado al codigo real de ~/Servidor/apps/catalogoia/app.py (verificado el 2026-09-06):

  - Objeto Flask               `app` (modulo app.py, no hay fabrica). `DB_PATH` sale del mismo modulo.
  - Base de datos              SQLite en DATA_DIR/catalogo.db (volumen `datos` -> /app/data).
  - Tabla de usuarios          usuarios(id, username, password_hash, nombre, creado). No hay columna de
                               correo ni de rol: el `username` es el correo con el que entra al panel y
                               todo usuario de esa tabla es administrador del Catalogo.
  - Algoritmo de la clave      werkzeug.security.check_password_hash (generate_password_hash al crear).
  - Inicio de sesion           session.clear(); _csrf nuevo; session["user_id"]; session["username"]
                               (identico a la vista `login` de app.py, incluida la rotacion de sesion).
  - CSRF                       app.py protege TODO POST con un token de formulario. El conector se exime
                               por ruta, envolviendo la funcion ya registrada (ver _eximir_csrf_del_conector).

Despliegue (docker-compose.servidor.yml del Catalogo), sin reconstruir la imagen:
    volumes:
      - ./observatorio/servidor_observatorio.py:/app/servidor_observatorio.py:ro
      - ./observatorio/observatorio_conector.py:/app/observatorio_conector.py:ro
    environment:
      OBS_CONECTOR_ACTIVO: "0"          # 1 para encender
      OBS_CONECTOR_SECRETO: "${OBS_CONECTOR_SECRETO_CATALOGO}"
    command: ["python", "servidor_observatorio.py"]

Reversa: quitar el `command:` (la imagen vuelve a su CMD `./arranque.sh`) y reiniciar el servicio.

Nota sobre los valores de un solo uso: waitress sirve la aplicacion en un unico proceso con varios hilos,
de modo que la memoria de nonces y jti del conector es correcta. Si algun dia el Catalogo pasa a varios
procesos, esa memoria debe moverse a un almacen compartido (ver observatorio_conector.py).
"""

import glob
import logging
import os
import secrets
import shutil
import sqlite3

from werkzeug.security import check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))


def _copiar_semilla():
    """Lo mismo que hace arranque.sh antes de arrancar: si el volumen de datos no tiene los JSON de
    semilla, los copia desde la imagen. Debe ejecutarse ANTES de importar app.py, porque al importarlo
    se ejecuta init_db(), que los lee."""
    origen = os.environ.get("SEED_ORIGEN", "/app/seed-inicial")
    if not os.path.isdir(origen):
        return
    destino = os.path.join(DATA_DIR, "seed")
    os.makedirs(destino, exist_ok=True)
    for archivo in glob.glob(os.path.join(origen, "*.json")):
        copia = os.path.join(destino, os.path.basename(archivo))
        if not os.path.exists(copia):
            shutil.copy2(archivo, copia)


_copiar_semilla()

from flask import request, session  # noqa: E402

from app import DB_PATH, app  # noqa: E402  (importar app.py ejecuta init_db(), como en servidor.py)
from observatorio_conector import crear_blueprint  # noqa: E402

PREFIJO = "/observatorio-conector"


# --------------------------------------------------------------------------
# Acceso de solo lectura a la base del Catalogo
# --------------------------------------------------------------------------
# Conexion propia y de corta vida: la del modulo app.py vive en `g` y solo existe dentro de una
# peticion con contexto de aplicacion. Se abre en modo lectura para que el conector no pueda escribir.

def _consultar(sql, parametros=()):
    conexion = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conexion.row_factory = sqlite3.Row
    try:
        return conexion.execute(sql, parametros).fetchall()
    finally:
        conexion.close()


def _uno(sql, parametros=()):
    filas = _consultar(sql, parametros)
    return filas[0] if filas else None


# --------------------------------------------------------------------------
# Usuarios: busqueda, verificacion de clave, apertura de sesion y perfil
# --------------------------------------------------------------------------
def _buscar_usuario(usuario):
    """El Catalogo identifica a sus usuarios por `username`, que en la practica es un correo."""
    return _uno("SELECT * FROM usuarios WHERE lower(username) = lower(?) LIMIT 1", (usuario or "",))


def _verificar_clave(u, clave):
    """La misma comprobacion de la vista login de app.py."""
    return bool(clave) and check_password_hash(u["password_hash"], clave)


def _buscar_por_identidad(id_externo, correo, usuario):
    """Para la apertura de sesion: primero por identificador, y si no, por el nombre de usuario."""
    if id_externo:
        fila = _uno("SELECT * FROM usuarios WHERE id = ?", (str(id_externo),))
        if fila:
            return fila
    for candidato in (correo, usuario):
        if candidato:
            fila = _buscar_usuario(candidato)
            if fila:
                return fila
    return None


def _iniciar_sesion(u):
    """Replica exactamente lo que hace el ingreso propio del Catalogo (app.py, vista `login`):
    limpia la sesion para evitar fijacion, genera un token CSRF nuevo y guarda usuario y nombre."""
    session.clear()
    session["_csrf"] = secrets.token_hex(16)
    session["user_id"] = u["id"]
    session["username"] = u["username"]
    return None  # el conector redirige a url_inicio


def _perfil(u):
    nombre_usuario = u["username"]
    return {
        "id": u["id"],
        "usuario": nombre_usuario,
        # No hay columna de correo: el nombre de usuario del Catalogo es el correo institucional.
        "correo": nombre_usuario if "@" in nombre_usuario else "",
        "nombre": (u["nombre"] or "").strip() or nombre_usuario,
        # Todo usuario de la tabla `usuarios` entra al panel /admin del Catalogo.
        "rol": "administrador",
    }


# --------------------------------------------------------------------------
# Conjuntos de datos de solo lectura para el cuadro de mando
# --------------------------------------------------------------------------
# Cada consulta devuelve solo lo necesario para los indicadores: nada de claves, correos, direcciones IP
# ni agentes de navegador. Donde hay una columna de fecha se llama `fecha`, que es la que el portal usa
# para construir las series mensuales, y se respeta el parametro `desde` para recolecciones incrementales.

def _filas(sql, parametros=()):
    return [dict(f) for f in _consultar(sql, parametros)]


def _fichas(desde):
    """Catalogo Unico de Oferta IA. `actualizacion` es la fecha declarada de la ficha y puede venir vacia."""
    sql = ("SELECT id, codigo, anio, categoria, tipo, entidad, naturaleza, publico, estado, "
           "verificado, actualizacion AS fecha FROM ofertas")
    if desde:
        return _filas(sql + " WHERE actualizacion >= ? ORDER BY id", (desde,))
    return _filas(sql + " ORDER BY id")


def _herramientas(desde):
    """Herramientas IA del repositorio. Sin fecha en el esquema."""
    return _filas("SELECT id, nombre, categoria, "
                  "CASE WHEN video <> '' THEN 1 ELSE 0 END AS con_video, "
                  "CASE WHEN enlace <> '' THEN 1 ELSE 0 END AS con_enlace "
                  "FROM herramientas ORDER BY id")


def _casos(desde):
    """Casos de exito: documentos PDF agrupados por carpeta. Sin fecha en el esquema."""
    return _filas("SELECT p.id, p.titulo, c.nombre AS carpeta "
                  "FROM casos_pdf p JOIN carpetas c ON c.id = p.carpeta_id ORDER BY c.orden, p.id")


def _usuarios(desde):
    """Usuarios del panel del Catalogo. Sin nombres de usuario ni claves."""
    sql = "SELECT id, 'administrador' AS rol, creado AS fecha FROM usuarios"
    if desde:
        return _filas(sql + " WHERE creado >= ? ORDER BY id", (desde,))
    return _filas(sql + " ORDER BY id")


def _consultas(desde):
    """Visitas publicas agregadas por dia y seccion. No sale ninguna direccion IP ni agente."""
    sql = "SELECT dia AS fecha, seccion, COUNT(*) AS visitas FROM visitas"
    if desde:
        return _filas(sql + " WHERE dia >= ? GROUP BY dia, seccion ORDER BY dia", (str(desde)[:10],))
    return _filas(sql + " GROUP BY dia, seccion ORDER BY dia")


# --------------------------------------------------------------------------
# Registro y exencion del CSRF propio del Catalogo
# --------------------------------------------------------------------------
def _bitacora(evento, detalle):
    """Deja constancia de cada llamada del portal en el registro del contenedor (docker logs
    catalogoia-web). No se escribe en la base del Catalogo para no tocar sus datos: las verificaciones
    fallidas del portal no deben contar en el limite de intentos de su pantalla de ingreso."""
    app.logger.info("observatorio %s %s", evento, detalle)


# app.py no usa el registro de Flask, que sale en nivel AVISO. Se baja a INFORMACION para que la
# bitacora del conector aparezca en `docker logs catalogoia-web`, una sola vez. Solo afecta a este registro.
app.logger.setLevel(logging.INFO)
app.logger.propagate = False


def _eximir_csrf_del_conector(aplicacion):
    """app.py protege con un token de formulario TODOS los POST (funcion `proteccion_csrf`, registrada
    con before_request). Las peticiones del portal no son formularios: van firmadas con HMAC-SHA256.
    En lugar de tocar app.py, se sustituye la funcion ya registrada por una envoltura que la llama para
    todo lo demas y la salta solo en la ruta del conector."""
    funciones = aplicacion.before_request_funcs.get(None, [])
    for i, original in enumerate(funciones):
        if getattr(original, "__name__", "") == "proteccion_csrf":
            def envoltura(_original=original):
                if request.path.rstrip("/") == PREFIJO:
                    return None
                return _original()
            envoltura.__name__ = "proteccion_csrf"
            funciones[i] = envoltura
            return True
    return False


conector = crear_blueprint(
    secreto=os.environ.get("OBS_CONECTOR_SECRETO", ""),
    activo=os.environ.get("OBS_CONECTOR_ACTIVO") == "1",
    buscar_usuario=_buscar_usuario,
    verificar_clave=_verificar_clave,
    buscar_por_identidad=_buscar_por_identidad,
    iniciar_sesion=_iniciar_sesion,
    perfil=_perfil,
    conjuntos={
        "fichas": ("Fichas del Catálogo Único de Oferta IA", _fichas),
        "herramientas": ("Herramientas de inteligencia artificial publicadas", _herramientas),
        "casos": ("Casos de éxito documentados", _casos),
        "usuarios": ("Usuarios del panel del Catálogo", _usuarios),
        "consultas": ("Visitas públicas por día y sección", _consultas),
    },
    # Los usuarios del Catalogo son administradores: la sesion abierta desde el portal se usa en el panel.
    url_inicio="/admin",
    bitacora=_bitacora,
)
app.register_blueprint(conector, url_prefix=PREFIJO)

if not _eximir_csrf_del_conector(app):
    app.logger.warning(
        "observatorio: no se encontró la comprobación CSRF de app.py (proteccion_csrf). "
        "El Catálogo funciona igual, pero el portal recibirá 400 al verificar claves. Revise app.py.")


if __name__ == "__main__":
    # Mismos parametros de produccion que servidor.py: waitress, 8 hilos y sin cabecera Server.
    from waitress import serve
    puerto = int(os.environ.get("PORT", 8080))
    print(f"Catálogo Digital IA escuchando en http://0.0.0.0:{puerto} (conector del Observatorio "
          f"{'activo' if os.environ.get('OBS_CONECTOR_ACTIVO') == '1' else 'apagado'})")
    serve(app, host="0.0.0.0", port=puerto, threads=8, ident=None)
