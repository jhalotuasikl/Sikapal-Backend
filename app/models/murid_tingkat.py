from app.extensions import db


class MuridTingkat(db.Model):
    __tablename__ = "murid_tingkat"

    id = db.Column(db.Integer, primary_key=True)

    id_murid = db.Column(
        db.Integer,
        db.ForeignKey("murid.id_murid"),
        nullable=False
    )

    id_tingkat = db.Column(
        db.Integer,
        db.ForeignKey("tingkat.id_tingkat"),
        nullable=False
    )

    id_kelas = db.Column(
        db.Integer,
        db.ForeignKey("kelas.id_kelas"),
        nullable=True
    )

    tahun_ajaran = db.Column(db.String(20))

    # aktif       = kelas yang sedang dijalani sekarang
    # selesai     = riwayat kelas/tahun ajaran lama yang sudah selesai
    # lulus       = murid sudah tamat sekolah
    # pindah      = murid pindah sekolah
    # tinggal_kelas = murid mengulang pada tingkat yang sama
    status = db.Column(
        db.Enum("aktif", "selesai", "lulus", "pindah", "tinggal_kelas"),
        default="aktif"
    )
