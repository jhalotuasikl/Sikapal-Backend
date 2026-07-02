from app import db

class User(db.Model):
    __tablename__ = 'users'

    id_user = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    id_role = db.Column(db.Integer, db.ForeignKey('roles.id_role'), nullable=False)

    foto_profil = db.Column(db.String(255), nullable=True)

    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
