# app/models/kehadiran_murid.py
from app.extensions import db
from datetime import date

class KehadiranMurid(db.Model):
    __tablename__ = "kehadiran_murid"
    __table_args__ = (
        db.UniqueConstraint(
            "id_jadwal",
            "id_murid",
            "semester",
            "tahun_ajaran",
            "pertemuan",
            name="uq_kehadiran_jadwal_murid_semester_ta_pertemuan",
        ),
    )

    id_kehadiran = db.Column(db.Integer, primary_key=True)

    id_jadwal = db.Column(db.Integer, db.ForeignKey("jadwal.id_jadwal"), nullable=False)
    id_murid = db.Column(db.Integer, db.ForeignKey("murid.id_murid"), nullable=False)

    semester = db.Column(db.Enum("ganjil", "genap"), nullable=False, default="ganjil", server_default="ganjil")
    tahun_ajaran = db.Column(db.String(20), nullable=False)

    tanggal = db.Column(db.Date, default=date.today, nullable=False)  # ✅ TAMBAH INI
    pertemuan = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)

    # Status ini membedakan input sementara guru dengan rekap yang sudah dikirim ke admin.
    # Default False: admin belum boleh melihat data ini di halaman hasil laporan.
    status_kirim = db.Column(db.Boolean, default=False, nullable=False)

    jadwal = db.relationship("Jadwal", back_populates="kehadiran")
    murid = db.relationship("Murid", back_populates="kehadiran")