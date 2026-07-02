from app.extensions import db
from app.models.kehadiran_murid import KehadiranMurid

class Jadwal(db.Model):
    __tablename__ = "jadwal"

    id_jadwal = db.Column(db.Integer, primary_key=True)
    id_kelas = db.Column(db.Integer, db.ForeignKey("kelas.id_kelas"))
    id_mapel = db.Column(db.Integer, db.ForeignKey("mata_pelajaran.id_mapel"))
    hari = db.Column(db.String(20))
    jam_mulai = db.Column(db.Time)
    jam_selesai = db.Column(db.Time)
    status = db.Column(db.String(20), nullable=False, default="aktif", server_default="aktif")

    
    kelas = db.relationship("Kelas", back_populates="jadwal")
    mapel = db.relationship("MataPelajaran", back_populates="jadwal")

    # relasi kehadiran murid
    kehadiran = db.relationship("KehadiranMurid", back_populates="jadwal")
    nilai = db.relationship("Nilai", back_populates="jadwal") 
    monitoring = db.relationship("LaporanMonitoring", back_populates="jadwal") # ✅ tambahkan ini
    jadwal_guru = db.relationship("JadwalGuru", back_populates="jadwal")