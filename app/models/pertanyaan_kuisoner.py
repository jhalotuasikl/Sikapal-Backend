from app.extensions import db
from datetime import datetime


class PertanyaanKuisoner(db.Model):
    __tablename__ = "pertanyaan_kuisoner"

    id_pertanyaan = db.Column(db.Integer, primary_key=True)
    pertanyaan = db.Column(db.Text, nullable=False)
    aktif = db.Column(db.Boolean, default=True)
    dibuat_pada = db.Column(db.DateTime, default=datetime.utcnow)