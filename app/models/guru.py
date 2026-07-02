from app.extensions import db
from app.models.guru_mapel import guru_mapel


class Guru(db.Model):
    __tablename__ = "guru"

    id_guru = db.Column(db.Integer, primary_key=True)
    nip = db.Column(db.String(50), unique=True, nullable=False)
    nama_guru = db.Column(db.String(100), nullable=False)

    id_user = db.Column(db.Integer, db.ForeignKey("users.id_user"), nullable=False)

    jadwal_guru = db.relationship("JadwalGuru", back_populates="guru")

    # relasi ke mapel
    mapel = db.relationship(
        "MataPelajaran",
        secondary=guru_mapel,
        back_populates="guru"
    )