from app.extensions import db
from app.models.guru_mapel import guru_mapel

class MataPelajaran(db.Model):
    __tablename__ = "mata_pelajaran"

    id_mapel = db.Column(db.Integer, primary_key=True)

    # ❌ jangan unique=True di sini
    nama_mapel = db.Column(db.String(100), nullable=False)

    id_tingkat = db.Column(db.Integer, db.ForeignKey("tingkat.id_tingkat"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("nama_mapel", "id_tingkat", name="uq_mapel_nama_tingkat"),
    )

    jadwal = db.relationship("Jadwal", back_populates="mapel")

    murid = db.relationship(
        "Murid",
        secondary="murid_mapel",
        back_populates="mapel"
    )

    guru = db.relationship(
        "Guru",
        secondary=guru_mapel,
        back_populates="mapel"
    )