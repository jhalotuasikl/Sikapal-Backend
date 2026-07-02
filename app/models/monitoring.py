from app.extensions import db
from datetime import date


class LaporanMonitoring(db.Model):
    __tablename__ = "laporan_monitoring"

    id_monitor = db.Column(db.Integer, primary_key=True)

    id_jadwal = db.Column(db.Integer, db.ForeignKey("jadwal.id_jadwal"))

    tanggal = db.Column(db.Date, default=date.today)

    jam_masuk = db.Column(db.Time)
    jam_keluar = db.Column(db.Time)

    status = db.Column(db.String(20))

    jadwal = db.relationship("Jadwal", back_populates="monitoring")

    def to_dict(self):
        return {
            "id_monitor": self.id_monitor,
            "id_jadwal": self.id_jadwal,
            "tanggal": str(self.tanggal) if self.tanggal else None,
            "jam_masuk": self.jam_masuk.strftime("%H:%M:%S") if self.jam_masuk else None,
            "jam_keluar": self.jam_keluar.strftime("%H:%M:%S") if self.jam_keluar else None,
            "status": self.status,
        }
