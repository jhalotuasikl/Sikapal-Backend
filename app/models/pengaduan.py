from app.extensions import db
from datetime import datetime
from sqlalchemy import text


class Pengaduan(db.Model):
    __tablename__ = "pengaduan"

    id_pengaduan = db.Column(db.Integer, primary_key=True)

    # Murid yang terkait dengan pengaduan.
    # Untuk pengaduan orang tua, kolom ini tetap diisi dengan id anak/murid.
    id_murid = db.Column(
        db.Integer,
        db.ForeignKey("murid.id_murid"),
        nullable=False
    )

    # Diisi hanya ketika pelapor adalah orang tua.
    id_ortu = db.Column(
        db.Integer,
        db.ForeignKey("orang_tua.id_ortu"),
        nullable=True
    )

    # Pembeda siapa yang mengirim pengaduan.
    # mode_pelaporan tetap dipakai untuk terbuka/rahasia/anonim.
    tipe_pelapor = db.Column(
        db.Enum("murid", "orang_tua", name="tipe_pelapor_pengaduan_enum"),
        nullable=False,
        default="murid"
    )

    jenis_laporan = db.Column(
        db.Enum("pengaduan", "aspirasi", name="jenis_laporan_pengaduan_enum"),
        nullable=False,
        default="pengaduan"
    )

    mode_pelaporan = db.Column(
        db.Enum("terbuka", "rahasia", "anonim", name="mode_pelaporan_enum"),
        nullable=False
    )

    kategori_pengaduan = db.Column(
        db.Enum(
            "akademik",
            "absensi",
            "nilai",
            "bullying",
            "fasilitas",
            "lainnya",
            name="kategori_pengaduan_enum"
        ),
        nullable=False
    )

    isi_pengaduan = db.Column(db.Text, nullable=False)

    status = db.Column(
        db.Enum(
            "menunggu",
            "diproses",
            "selesai",
            "ditolak",
            name="status_pengaduan_enum"
        ),
        nullable=False,
        default="menunggu"
    )

    catatan_admin = db.Column(db.Text, nullable=True)

    tanggal_pengaduan = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    tanggal_ditindaklanjuti = db.Column(
        db.DateTime,
        nullable=True
    )

    murid = db.relationship("Murid", backref="pengaduan_list", lazy=True)

    def _get_nama_ortu(self):
        if not self.id_ortu:
            return None

        try:
            row = db.session.execute(
                text("SELECT nama_ortu FROM orang_tua WHERE id_ortu = :id_ortu LIMIT 1"),
                {"id_ortu": self.id_ortu},
            ).mappings().first()
            if row:
                return row.get("nama_ortu")
        except Exception:
            return None

        return None

    def to_dict(self):
        nama_murid = self.murid.nama_murid if self.murid else None
        nis = self.murid.nis if self.murid else None
        id_kelas = self.murid.id_kelas if self.murid else None
        nama_kelas = (
            self.murid.kelas.nama_kelas
            if self.murid and self.murid.kelas
            else None
        )
        nama_ortu = self._get_nama_ortu()

        if self.tipe_pelapor == "orang_tua":
            if nama_murid:
                pelapor_display = f"Orang tua dari {nama_murid}"
            else:
                pelapor_display = "Orang tua"
        else:
            pelapor_display = nama_murid or "Murid"

        return {
            "id_pengaduan": self.id_pengaduan,
            "id_murid": self.id_murid,
            "id_ortu": self.id_ortu,
            "tipe_pelapor": self.tipe_pelapor,
            "jenis_laporan": self.jenis_laporan,
            "pelapor_display": pelapor_display,
            "nama_ortu": nama_ortu,
            "nama_murid": nama_murid,
            "nis": nis,
            "id_kelas": id_kelas,
            "nama_kelas": nama_kelas,
            "mode_pelaporan": self.mode_pelaporan,
            "kategori_pengaduan": self.kategori_pengaduan,
            "isi_pengaduan": self.isi_pengaduan,
            "status": self.status,
            "catatan_admin": self.catatan_admin,
            "tanggal_pengaduan": self.tanggal_pengaduan.strftime("%Y-%m-%d %H:%M:%S") if self.tanggal_pengaduan else None,
            "tanggal_ditindaklanjuti": self.tanggal_ditindaklanjuti.strftime("%Y-%m-%d %H:%M:%S") if self.tanggal_ditindaklanjuti else None,
        }
