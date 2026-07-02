from app.extensions import db

kelas_mapel = db.Table(
    "kelas_mapel",
    db.Column("id_kelas", db.Integer, db.ForeignKey("kelas.id_kelas"), primary_key=True),
    db.Column("id_mapel", db.Integer, db.ForeignKey("mata_pelajaran.id_mapel"), primary_key=True),
)