from datetime import datetime, timezone
from src.models.database import db
class Entity(db.Model):
    __tablename__ = "entities"
    id = db.Column(db.Integer, primary_key=True)
    divipola_code = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(500), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(120), default="")
    entity_type = db.Column(db.String(50), default="municipio")
    category = db.Column(db.String(10), default="")
    website_url = db.Column(db.String(500), default="")
    status = db.Column(db.String(20), default="active")
    parent_id = db.Column(db.Integer, db.ForeignKey("entities.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
