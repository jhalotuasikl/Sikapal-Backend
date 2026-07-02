from app.extensions import db


class MuridMapel(db.Model):
    __tablename__ = "murid_mapel"
    __table_args__ = (
        db.UniqueConstraint(
            "id_murid",
            "id_mapel",
            name="uq_murid_mapel_murid_mapel",
        ),
    )

    id_murid_mapel = db.Column(db.Integer, primary_key=True)

    id_murid = db.Column(
        db.Integer,
        db.ForeignKey("murid.id_murid", ondelete="CASCADE"),
        nullable=False
    )

    id_mapel = db.Column(
        db.Integer,
        db.ForeignKey("mata_pelajaran.id_mapel", ondelete="CASCADE"),
        nullable=False
    )