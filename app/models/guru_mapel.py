from app.extensions import db

guru_mapel = db.Table(
    "guru_mapel",
    db.Column("id_guru", db.Integer, db.ForeignKey("guru.id_guru"), primary_key=True),
    db.Column("id_mapel", db.Integer, db.ForeignKey("mata_pelajaran.id_mapel"), primary_key=True),
)