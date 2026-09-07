"""Fabrica simulada con la misma forma que web/app.py de mintic1519."""
import os, sys
from datetime import datetime, timezone
from flask import Flask, request, redirect, url_for
from flask_login import LoginManager, login_user, current_user
from flask_wtf.csrf import CSRFProtect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.models.database import db

login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="clave-de-prueba", SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:////tmp/claude-0/mintic-prueba.sqlite"), WTF_CSRF_CHECK_DEFAULT=True)
    db.init_app(app); login_manager.init_app(app); csrf.init_app(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(uid):
        from src.models.user import User
        return User.query.get(int(uid))

    @app.route("/admin/")
    def dashboard():
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        return f"<h1>Solución Automatizada</h1><p>Sesión de: {current_user.name} ({current_user.email})</p>"

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        from src.models.user import User
        if request.method == "POST":
            u = User.query.filter_by(email=request.form.get("email", ""), is_active=True).first()
            if u and u.check_password(request.form.get("password", "")):
                login_user(u); return redirect("/admin/")
            return "Credenciales inválidas", 401
        return "<form method=post><input name=email><input name=password type=password><button>Entrar</button></form>"
    csrf.exempt(login)  # en la app real el formulario lleva el token; aqui se exime para la prueba por curl

    with app.app_context():
        from src.models.user import User
        from src.models.entity import Entity
        from src.models.evaluation import Evaluation
        from src.models.consolidation import Consolidation
        db.drop_all(); db.create_all()
        for e, n, r, p in [("jmartinez@cartagena.gov.co", "Julián Martínez", "viewer", "Clave.2026"), ("jvergaras@unicartagena.edu.co", "Juan Carlos Vergara", "admin", "Admin.2026")]:
            u = User(email=e, name=n, role=r, is_active=True); u.set_password(p); db.session.add(u)
        for i in range(1, 41):
            db.session.add(Entity(divipola_code=f"13{i:03d}", name=f"Alcaldía {i}", department=["Bolívar", "Atlántico", "Córdoba"][i % 3], city=f"Municipio {i}", website_url="https://x" if i % 4 else ""))
        db.session.flush()
        for i in range(1, 61):
            db.session.add(Evaluation(entity_id=(i % 40) + 1, total_score=0.3 + (i % 7) / 10, period="2026-Q1" if i % 2 else "2026-Q2", evaluated_at=datetime(2026, 1 + (i % 8), 1 + (i % 27), tzinfo=timezone.utc)))
        db.session.add(Consolidation(entity_id=1, period="2026-ANUAL", total_score=0.7, evaluations_count=3, rank_national=5, rank_department=1, trend="avance"))
        db.session.commit()
    return app
