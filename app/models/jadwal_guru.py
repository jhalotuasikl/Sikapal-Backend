from app.extensions import db

class JadwalGuru(db.Model):
    __tablename__ = "jadwal_guru"
    __table_args__ = (
        db.UniqueConstraint("id_jadwal", "id_guru", name="uq_jadwal_guru"),
    )

    id_jadwal_guru = db.Column(db.Integer, primary_key=True)
    id_jadwal = db.Column(db.Integer, db.ForeignKey("jadwal.id_jadwal"), nullable=False)
    id_guru = db.Column(db.Integer, db.ForeignKey("guru.id_guru"), nullable=False)

    jadwal = db.relationship("Jadwal", back_populates="jadwal_guru")
    guru = db.relationship("Guru", back_populates="jadwal_guru")