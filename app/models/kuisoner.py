from app.extensions import db
from datetime import datetime


class Kuisoner(db.Model):
    __tablename__ = "kuisoner"

    id_kuisoner = db.Column(db.Integer, primary_key=True)
    id_jadwal = db.Column(
        db.Integer,
        db.ForeignKey("jadwal.id_jadwal", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False
    )
    semester = db.Column(db.String(10), nullable=False)
    tahun_ajaran = db.Column(db.String(20), nullable=False)

    status = db.Column(
        db.Enum("belum_dibuka", "dibuka", "ditutup", "selesai", name="status_kuisoner_enum"),
        default="belum_dibuka",
        nullable=False
    )

    tanggal_dibuka = db.Column(db.DateTime, nullable=True)
    tanggal_ditutup = db.Column(db.DateTime, nullable=True)

    dibuat_pada = db.Column(db.DateTime, default=datetime.utcnow)
    diupdate_pada = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    jawaban = db.relationship(
        "JawabanKuisoner",
        backref="kuisoner",
        cascade="all, delete-orphan",
        lazy=True
    )