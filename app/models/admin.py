from app import db


class Admin(db.Model):
    __tablename__ = "admin"

    id_admin = db.Column(db.Integer, primary_key=True)
    nama_admin = db.Column(db.String(100), nullable=False)
    id_user = db.Column(
        db.Integer,
        db.ForeignKey("users.id_user", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = db.Column(
        db.Enum("aktif", "tidak aktif", name="enum_admin_status"),
        nullable=False,
        default="aktif",
        server_default="aktif",
    )
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    user = db.relationship(
        "User",
        backref=db.backref("admin_profile", uselist=False),
    )