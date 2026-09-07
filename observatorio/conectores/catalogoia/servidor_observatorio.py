"""
Punto de entrada de la aplicacion Catalogo de IA (catalogoia) con el conector del Observatorio montado.

No modifica ningun archivo de la aplicacion. Importa la aplicacion Flask ya construida y le registra
el conector como blueprint. Sirve la misma aplicacion con waitress, igual que arranque.sh.

IMPORTANTE. Este archivo depende de como la aplicacion catalogoia expone su objeto Flask, su modelo de
usuarios, su verificacion de clave y su forma de iniciar sesion. Esos cuatro puntos se completan abajo,
en las funciones marcadas con AJUSTAR, a partir del codigo real de catalogoia (app.py o servidor.py).
Mientras no se completen, el conector responde pero la verificacion no reconocera usuarios.

Despliegue (docker-compose.servidor.yml del Catalogo), sin reconstruir la imagen:
    volumes:
      - ./observatorio/servidor_observatorio.py:/app/servidor_observatorio.py:ro
      - ./observatorio/observatorio_conector.py:/app/observatorio_conector.py:ro
    environment:
      OBS_CONECTOR_ACTIVO: "0"          # 1 para encender
      OBS_CONECTOR_SECRETO: "${OBS_CONECTOR_SECRETO_CATALOGO}"
    command: python servidor_observatorio.py

Reversa: volver a `command: ./arranque.sh` (o el comando original) y reiniciar el servicio.
"""

import os

# La aplicacion Flask de catalogoia. Segun app.py, el objeto se llama `app`.
# Si catalogoia usa una fabrica create_app(), sustituya por: from app import create_app; app = create_app()
from app import app  # AJUSTAR si el objeto Flask tiene otro nombre o se crea con una fabrica

from observatorio_conector import crear_blueprint


# --- AJUSTAR: modelo de usuarios y verificacion de clave de catalogoia ---
# catalogoia guarda sus datos en SQLite dentro de /app/data. Complete estas funciones con el acceso real.
# Ejemplo tipico con sqlite3 y werkzeug (ajuste nombres de tabla y columnas a los reales de catalogoia):

import sqlite3
from werkzeug.security import check_password_hash

RUTA_BD = os.environ.get("DATA_DIR", "/app/data") + "/catalogo.sqlite"  # AJUSTAR nombre del archivo


def _conn():
    c = sqlite3.connect(RUTA_BD)
    c.row_factory = sqlite3.Row
    return c


def _buscar_usuario(usuario):
    with _conn() as c:
        return c.execute(
            "SELECT * FROM usuarios WHERE lower(correo) = lower(?) OR lower(usuario) = lower(?) LIMIT 1",  # AJUSTAR
            (usuario, usuario),
        ).fetchone()


def _verificar_clave(u, clave):
    # AJUSTAR al esquema real: puede ser check_password_hash, bcrypt, o el metodo propio de catalogoia.
    return bool(clave) and check_password_hash(u["clave_hash"], clave)


def _buscar_por_identidad(id_externo, correo, usuario):
    with _conn() as c:
        if id_externo:
            r = c.execute("SELECT * FROM usuarios WHERE id = ?", (id_externo,)).fetchone()
            if r:
                return r
        if correo:
            return c.execute("SELECT * FROM usuarios WHERE lower(correo) = lower(?)", (correo,)).fetchone()
    return None


def _iniciar_sesion(u):
    # AJUSTAR: replicar exactamente lo que hace el login de catalogoia (normalmente session["user_id"] = u["id"]).
    from flask import session
    session["user_id"] = u["id"]
    session.permanent = True
    return None  # el conector redirige a url_inicio


def _perfil(u):
    return {"id": u["id"], "usuario": u["correo"], "correo": u["correo"],
            "nombre": u["nombre"] if "nombre" in u.keys() else u["correo"],
            "rol": u["rol"] if "rol" in u.keys() else "usuario"}


# --- Conjuntos de datos de solo lectura para el cuadro de mando ---
# AJUSTAR nombres de tablas y columnas a los reales de catalogoia.

def _fichas(desde):
    with _conn() as c:
        filas = c.execute("SELECT id, tipo, categoria, estado, fecha, entidad FROM fichas").fetchall()  # AJUSTAR
    return [dict(f) for f in filas]


def _usuarios(desde):
    with _conn() as c:
        filas = c.execute("SELECT id, rol, fecha FROM usuarios").fetchall()  # AJUSTAR (sin correos ni nombres)
    return [dict(f) for f in filas]


conector = crear_blueprint(
    secreto=os.environ.get("OBS_CONECTOR_SECRETO", ""),
    activo=os.environ.get("OBS_CONECTOR_ACTIVO") == "1",
    buscar_usuario=_buscar_usuario,
    verificar_clave=_verificar_clave,
    buscar_por_identidad=_buscar_por_identidad,
    iniciar_sesion=_iniciar_sesion,
    perfil=_perfil,
    conjuntos={
        "fichas": ("Fichas del catálogo", _fichas),
        "usuarios": ("Usuarios de la aplicación", _usuarios),
    },
    url_inicio="/",
)
app.register_blueprint(conector, url_prefix="/observatorio-conector")

# Si catalogoia usa Flask-WTF CSRFProtect, eximir el blueprint (busque el objeto csrf en app.py):
try:
    from app import csrf  # AJUSTAR o elimine si catalogoia no usa CSRFProtect
    csrf.exempt(conector)
except Exception:
    pass


if __name__ == "__main__":
    # Mismo servidor de produccion que arranque.sh (waitress), en el mismo puerto interno 8080.
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
