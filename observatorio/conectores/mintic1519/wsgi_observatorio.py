"""
Punto de entrada WSGI de la Solucion Automatizada (mintic1519) con el conector del Observatorio montado.

No modifica ningun archivo de la aplicacion. Importa la aplicacion ya construida por wsgi.py,
le registra el conector como blueprint y la expone como `app` para gunicorn.

Despliegue (docker-compose.servidor.yml del servicio web), sin reconstruir la imagen:
    volumes:
      - ./observatorio/wsgi_observatorio.py:/app/wsgi_observatorio.py:ro
      - ./observatorio/observatorio_conector.py:/app/observatorio_conector.py:ro
    environment:
      OBS_CONECTOR_ACTIVO: "0"          # 1 para encender
      OBS_CONECTOR_SECRETO: "${OBS_CONECTOR_SECRETO_SOLUCION}"
    command: gunicorn wsgi_observatorio:app -w 1 --threads 16 --timeout 0 -b 0.0.0.0:8000 --access-logfile -

Reversa: volver a `command: gunicorn wsgi:app ...` y reiniciar el servicio.
"""

import os
from datetime import datetime, timezone

from wsgi import app  # aplicacion Flask ya configurada por la propia Solucion Automatizada

from observatorio_conector import crear_blueprint


def _f(d):
    """Fecha en formato ISO corto para el portal, o cadena vacia."""
    return d.strftime("%Y-%m-%d") if d else ""


def _buscar_usuario(usuario):
    from src.models.user import User
    u = User.query.filter_by(email=usuario, is_active=True).first()
    if not u:
        u = User.query.filter(User.name.ilike(usuario), User.is_active == True).first()  # noqa: E712
    return u


def _verificar_clave(u, clave):
    return bool(clave) and u.check_password(clave)


def _buscar_por_identidad(id_externo, correo, usuario):
    from src.models.user import User
    u = None
    if id_externo and str(id_externo).isdigit():
        u = User.query.filter_by(id=int(id_externo), is_active=True).first()
    if not u and correo:
        u = User.query.filter_by(email=correo, is_active=True).first()
    return u


def _iniciar_sesion(u):
    # Misma rutina que usa la pantalla de ingreso de la aplicacion.
    from flask_login import login_user
    from src.models.database import db
    login_user(u)
    u.last_login = datetime.now(timezone.utc)
    db.session.commit()
    try:
        from src.services.audit_service import log_action
        log_action("login_portal_observatorio", "user", str(u.id))
    except Exception:
        pass
    return None  # el conector redirige a url_inicio


def _perfil(u):
    return {"id": u.id, "usuario": u.email, "correo": u.email, "nombre": u.name or u.email, "rol": u.role}


# --- Conjuntos de datos de solo lectura para el cuadro de mando del Observatorio ---

def _entidades(desde):
    from src.models.entity import Entity
    q = Entity.query.filter(Entity.parent_id.is_(None))
    return [{"id": e.id, "divipola": e.divipola_code, "nombre": e.name, "departamento": e.department,
             "municipio": e.city or "", "tipo": e.entity_type, "categoria": e.category or "",
             "estado": e.status, "tiene_sitio": bool(e.website_url), "fecha": _f(e.created_at)}
            for e in q.order_by(Entity.department, Entity.name).all()]


def _evaluaciones(desde):
    from src.models.evaluation import Evaluation
    q = Evaluation.query.order_by(Evaluation.evaluated_at.desc()).limit(5000)
    return [{"id": ev.id, "entidad_id": ev.entity_id, "periodo": ev.period or "", "origen": ev.source,
             "estado": ev.status, "puntaje": round(ev.total_score or 0, 3),
             "puntajes_categoria": ev.category_scores or {}, "fecha": _f(ev.evaluated_at)}
            for ev in q.all()]


def _consolidaciones(desde):
    from src.models.consolidation import Consolidation
    return [{"id": c.id, "entidad_id": c.entity_id, "periodo": c.period, "puntaje": round(c.total_score or 0, 3),
             "evaluaciones": c.evaluations_count, "puesto_nacional": c.rank_national,
             "puesto_departamento": c.rank_department, "tendencia": c.trend, "fecha": _f(c.consolidated_at)}
            for c in Consolidation.query.all()]


def _usuarios(desde):
    from src.models.user import User
    # Sin correos ni nombres: solo lo necesario para contar y graficar.
    return [{"id": u.id, "rol": u.role, "activo": bool(u.is_active), "fecha": _f(u.created_at),
             "ultimo_ingreso": _f(u.last_login)} for u in User.query.all()]


def _bitacora(evento, detalle):
    try:
        from src.services.audit_service import log_action
        log_action("conector_" + evento, "observatorio", "", details=detalle)
    except Exception:
        pass


conector = crear_blueprint(
    secreto=os.environ.get("OBS_CONECTOR_SECRETO", ""),
    activo=os.environ.get("OBS_CONECTOR_ACTIVO") == "1",
    buscar_usuario=_buscar_usuario,
    verificar_clave=_verificar_clave,
    buscar_por_identidad=_buscar_por_identidad,
    iniciar_sesion=_iniciar_sesion,
    perfil=_perfil,
    conjuntos={
        "entidades": ("Entidades territoriales registradas", _entidades),
        "evaluaciones": ("Evaluaciones de cumplimiento realizadas", _evaluaciones),
        "consolidaciones": ("Consolidados por periodo", _consolidaciones),
        "usuarios": ("Usuarios de la aplicación", _usuarios),
    },
    url_inicio="/admin/",
    bitacora=_bitacora,
)

app.register_blueprint(conector, url_prefix="/observatorio-conector")

# La aplicacion protege los formularios con Flask-WTF. Las llamadas del portal van firmadas con HMAC,
# asi que el conector queda exento de esa proteccion, igual que la API REST de la propia aplicacion.
try:
    from web.app import csrf
    csrf.exempt(conector)
except Exception:
    pass
