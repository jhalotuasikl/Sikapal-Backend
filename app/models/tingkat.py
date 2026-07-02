from app import db

class Tingkat(db.Model):
    __tablename__ = "tingkat"

    id_tingkat = db.Column(db.Integer, primary_key=True)
    pangkat = db.Column(db.String(10), nullable=False)

    murid = db.relationship(
    "MuridTingkat",
    backref="tingkat"
)