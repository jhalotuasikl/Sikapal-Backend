from app.extensions import db
from app.models.kelas_guru import kelas_guru
from app.models.kelas_mapel import kelas_mapel
from app.models.murid_tingkat import MuridTingkat

class Kelas(db.Model):
    __tablename__ = "kelas"

    id_kelas = db.Column(db.Integer, primary_key=True)
    nama_kelas = db.Column(db.String(100), nullable=False)
    tahun_ajaran = db.Column(db.String(20), nullable=False)
    id_tingkat = db.Column(db.Integer, db.ForeignKey("tingkat.id_tingkat"))
    status = db.Column(db.String(20), nullable=False, default="aktif", server_default="aktif")

    jadwal = db.relationship("Jadwal", back_populates="kelas")
    murid = db.relationship("Murid", back_populates="kelas")

    tingkat = db.relationship("Tingkat", backref="kelas")  # <--- ini penting

    # # RELATIONSHIP MANY-TO-MANY
    guru = db.relationship(
        "Guru",
        secondary=kelas_guru,
        backref=db.backref("kelas", lazy="dynamic"),
        lazy="dynamic"
    )
    
    mapel = db.relationship(
        "MataPelajaran",
        secondary=kelas_mapel,
        backref=db.backref("kelas", lazy="dynamic"),
        lazy="dynamic"
    )

    murid_tingkat = db.relationship(
    "MuridTingkat",
    backref="kelas"
)