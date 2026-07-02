# app/models/nilai.py
from app.extensions import db

class Nilai(db.Model):
    __tablename__ = "nilai"
    __table_args__ = (
        db.UniqueConstraint(
            "id_jadwal",
            "id_murid",
            "semester",
            "tahun_ajaran",
            name="uq_nilai_jadwal_murid_semester_ta",
        ),
    )

    id_nilai = db.Column(db.Integer, primary_key=True)

    id_jadwal = db.Column(db.Integer, db.ForeignKey("jadwal.id_jadwal"), nullable=False)
    id_murid  = db.Column(db.Integer, db.ForeignKey("murid.id_murid"), nullable=False)

    semester     = db.Column(db.String(20), nullable=False)
    tahun_ajaran = db.Column(db.String(20), nullable=False)

    nilai_angka = db.Column(db.Float, nullable=False)
    nilai_huruf = db.Column(db.String(2), nullable=False)

    status_kirim = db.Column(db.Boolean, default=False, nullable=False)  # ✅ TAMBAH

    jadwal = db.relationship("Jadwal", back_populates="nilai")