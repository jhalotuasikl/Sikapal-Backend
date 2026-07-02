from app.extensions import db


class DetailJawabanKuisoner(db.Model):
    __tablename__ = "detail_jawaban_kuisoner"

    id_detail_jawaban = db.Column(db.Integer, primary_key=True)

    id_jawaban = db.Column(
        db.Integer,
        db.ForeignKey("jawaban_kuisoner.id_jawaban", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False
    )

    id_pertanyaan = db.Column(
        db.Integer,
        db.ForeignKey("pertanyaan_kuisoner.id_pertanyaan", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False
    )

    pilihan = db.Column(
        db.Enum("A", "B", "C", "D", name="pilihan_kuisoner_enum"),
        nullable=False
    )

    skor = db.Column(db.Integer, nullable=False)