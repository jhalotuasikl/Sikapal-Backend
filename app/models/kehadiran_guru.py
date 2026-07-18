from app.extensions import db
from datetime import date


class KehadiranGuru(db.Model):
    __tablename__ = "kehadiran_guru"
    __table_args__ = (
        db.UniqueConstraint(
            "id_guru",
            "id_jadwal",
            "tanggal",
            name="uq_kehadiran_guru_per_jadwal"
        ),
    )

    id_kehadiran = db.Column(db.Integer, primary_key=True)

    id_guru = db.Column(
        db.Integer,
        db.ForeignKey("guru.id_guru"),
        nullable=False
    )

    id_jadwal = db.Column(
        db.Integer,
        db.ForeignKey("jadwal.id_jadwal"),
        nullable=True
    )

    tanggal = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(30), nullable=False, default="Hadir")
    keterangan = db.Column(db.String(255), nullable=True)
    alasan = db.Column(db.Text, nullable=True)
    instruksi = db.Column(db.Text, nullable=True)
    bukti = db.Column(db.String(255), nullable=True)
    status_pengajuan = db.Column(db.String(30), nullable=True)

    guru = db.relationship(
        "Guru",
        backref=db.backref("kehadiran_guru", lazy=True)
    )

    jadwal = db.relationship(
        "Jadwal",
        backref=db.backref("kehadiran_guru", lazy=True)
    )

    def to_dict(self):
        return {
            "id_kehadiran": self.id_kehadiran,
            "id_guru": self.id_guru,
            "id_jadwal": self.id_jadwal,
            "tanggal": str(self.tanggal) if self.tanggal else None,
            "status": self.status,
            "keterangan": self.keterangan,
            "alasan": self.alasan,
            "instruksi": self.instruksi,
            "bukti": self.bukti,
            "status_pengajuan": self.status_pengajuan,
        }
