from datetime import datetime, timezone
import bcrypt
from flask_login import UserMixin
from src.models.database import db

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200), default="")
    role = db.Column(db.String(20), default="viewer")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    def set_password(self, p): self.password_hash = bcrypt.hashpw(p.encode(), bcrypt.gensalt(rounds=4)).decode()
    def check_password(self, p): return bcrypt.checkpw(p.encode(), self.password_hash.encode())
