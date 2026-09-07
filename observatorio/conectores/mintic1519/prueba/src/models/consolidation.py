from datetime import datetime, timezone
from src.models.database import db
class Consolidation(db.Model):
    __tablename__ = "consolidations"
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, nullable=False)
    period = db.Column(db.String(20), nullable=False)
    total_score = db.Column(db.Float, default=0.0)
    evaluations_count = db.Column(db.Integer, default=0)
    rank_national = db.Column(db.Integer, default=0)
    rank_department = db.Column(db.Integer, default=0)
    trend = db.Column(db.String(20), default="sin_datos")
    consolidated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
