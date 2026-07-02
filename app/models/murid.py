from app.extensions import db
from app.models.kehadiran_murid import KehadiranMurid
from app.models.murid_mapel import MuridMapel


class Murid(db.Model):
    __tablename__ = "murid"

    id_murid = db.Column(db.Integer, primary_key=True)
    nis = db.Column(db.String(50), unique=True)
    nama_murid = db.Column(db.String(100))
    id_user = db.Column(db.Integer, db.ForeignKey("users.id_user"))
    id_kelas = db.Column(db.Integer, db.ForeignKey("kelas.id_kelas"))

    kelas = db.relationship("Kelas", back_populates="murid")
    kehadiran = db.relationship("KehadiranMurid", back_populates="murid")
    

    # ✅ RELASI MANY TO MANY KE MAPEL
    mapel = db.relationship(
        "MataPelajaran",
        secondary="murid_mapel",
        back_populates="murid"
    )

    tingkat = db.relationship(
    "MuridTingkat",
    backref="murid",
    cascade="all, delete-orphan"
)

   
