from app.extensions import db
from datetime import datetime


class JawabanKuisoner(db.Model):
    __tablename__ = "jawaban_kuisoner"

    id_jawaban = db.Column(db.Integer, primary_key=True)

    id_kuisoner = db.Column(
        db.Integer,
        db.ForeignKey("kuisoner.id_kuisoner", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False
    )

    id_murid = db.Column(
        db.Integer,
        db.ForeignKey("murid.id_murid", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False
    )

    tanggal_kirim = db.Column(db.DateTime, default=datetime.utcnow)

    detail_jawaban = db.relationship(
        "DetailJawabanKuisoner",
        backref="jawaban",
        cascade="all, delete-orphan",
        lazy=True
    )

    __table_args__ = (
        db.UniqueConstraint("id_kuisoner", "id_murid", name="unik_murid_isi_kuisoner"),
    )