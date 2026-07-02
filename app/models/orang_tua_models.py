from app import db


class OrangTua(db.Model):
    __tablename__ = 'orang_tua'

    id_ortu = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama_ortu = db.Column(db.String(100), nullable=False)
    no_hp = db.Column(db.String(20), nullable=True)

    id_murid = db.Column(
        db.Integer,
        db.ForeignKey('murid.id_murid'),
        nullable=False
    )

    id_user = db.Column(
        db.Integer,
        db.ForeignKey('users.id_user'),
        nullable=False
    )

    # Relasi ke tabel murid
    murid = db.relationship(
        'Murid',
        backref=db.backref('orang_tua', lazy=True)
    )

    # Relasi ke tabel users
    user = db.relationship(
        'User',
        backref=db.backref('orang_tua', lazy=True)
    )

    def to_dict(self):
        return {
            'id_ortu': self.id_ortu,
            'nama_ortu': self.nama_ortu,
            'no_hp': self.no_hp,
            'id_murid': self.id_murid,
            'id_user': self.id_user,
            'username': self.user.username if self.user else None,
            'nama_murid': self.murid.nama_murid if self.murid else None
        }