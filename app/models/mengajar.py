from app.extensions import db
from datetime import datetime


class LaporanMengajar(db.Model):
    __tablename__ = "laporan_mengajar"

    id_laporan = db.Column(db.Integer, primary_key=True)

    id_monitor = db.Column(
        db.Integer,
        db.ForeignKey("laporan_monitoring.id_monitor"),
        nullable=False,
        unique=True
    )

    materi = db.Column(db.Text, nullable=False)
    catatan = db.Column(db.Text, nullable=True)

    jumlah_hadir = db.Column(db.Integer, nullable=False, default=0)
    jumlah_tidak_hadir = db.Column(db.Integer, nullable=False, default=0)

    # Jika guru mengaktifkan toggle "membawa data kehadiran",
    # daftar murid hadir/tidak hadir dari input kehadiran murid akan disimpan di sini.
    bawa_data_kehadiran = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="0"
    )
    daftar_hadir = db.Column(db.Text, nullable=True)
    daftar_tidak_hadir = db.Column(db.Text, nullable=True)

    waktu_input = db.Column(
        db.DateTime,
        default=datetime.now,
        onupdate=datetime.now
    )

    monitoring = db.relationship(
        "LaporanMonitoring",
        backref=db.backref("laporan_mengajar", uselist=False, lazy=True)
    )

    def to_dict(self):
        return {
            "id_laporan": self.id_laporan,
            "id_monitor": self.id_monitor,
            "materi": self.materi,
            "catatan": self.catatan,
            "jumlah_hadir": self.jumlah_hadir,
            "jumlah_tidak_hadir": self.jumlah_tidak_hadir,
            "bawa_data_kehadiran": bool(self.bawa_data_kehadiran),
            "daftar_hadir": self.daftar_hadir,
            "daftar_tidak_hadir": self.daftar_tidak_hadir,
            "waktu_input": self.waktu_input.strftime("%Y-%m-%d %H:%M:%S")
            if self.waktu_input else None,
        }