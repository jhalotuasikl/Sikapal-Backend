from app.extensions import db

kelas_guru = db.Table(
    "kelas_guru",
    db.Column("id_kelas", db.Integer, db.ForeignKey("kelas.id_kelas"), primary_key=True),
    db.Column("id_guru", db.Integer, db.ForeignKey("guru.id_guru"), primary_key=True)
)