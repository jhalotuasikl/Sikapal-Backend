from app import db

class Role(db.Model):
    __tablename__ = 'roles'

    id_role = db.Column(db.Integer, primary_key=True)
    nama_role = db.Column(db.String(50), unique=True, nullable=False)
