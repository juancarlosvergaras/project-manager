from datetime import datetime, timezone
from src.models.database import db
class Evaluation(db.Model):
    __tablename__ = "evaluations"
    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id"), nullable=False)
    total_score = db.Column(db.Float, default=0.0)
    category_scores = db.Column(db.JSON, default=dict)
    period = db.Column(db.String(20), default="")
    source = db.Column(db.String(20), default="sistema")
    status = db.Column(db.String(20), default="completed")
    evaluated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
