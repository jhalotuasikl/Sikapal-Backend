# app/models/periode_akademik.py
from app import db


class PeriodeAkademik(db.Model):
    __tablename__ = "periode_akademik"

    id_periode = db.Column(db.Integer, primary_key=True)
    tahun_ajaran = db.Column(db.String(20), nullable=False)
    semester = db.Column(db.Enum("ganjil", "genap"), nullable=False)
    tanggal_mulai = db.Column(db.Date, nullable=False)
    tanggal_selesai = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.Enum("aktif", "selesai"),
        nullable=False,
        default="selesai",
        server_default="selesai",
    )

    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    @staticmethod
    def aktif():
        return PeriodeAkademik.query.filter_by(status="aktif").first()

    def to_dict(self):
        return {
            "id_periode": self.id_periode,
            "tahun_ajaran": self.tahun_ajaran,
            "semester": self.semester,
            "semester_label": "Ganjil" if self.semester == "ganjil" else "Genap",
            "tanggal_mulai": self.tanggal_mulai.isoformat() if self.tanggal_mulai else None,
            "tanggal_selesai": self.tanggal_selesai.isoformat() if self.tanggal_selesai else None,
            "status": self.status,
            "label": f"Semester {'Ganjil' if self.semester == 'ganjil' else 'Genap'} • TA {self.tahun_ajaran}",
        }
