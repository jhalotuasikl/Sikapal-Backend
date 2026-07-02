from app.extensions import db


# Tabel many-to-many
jadwal_murid = db.Table(
    "jadwal_murid",
    db.Column("id_jadwal", db.Integer, db.ForeignKey("jadwal.id_jadwal"), primary_key=True),
    db.Column("id_murid", db.Integer, db.ForeignKey("murid.id_murid"), primary_key=True)
)