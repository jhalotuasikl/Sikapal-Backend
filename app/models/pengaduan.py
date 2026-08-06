import json
from datetime import datetime

from sqlalchemy import text

from app.extensions import db


class Pengaduan(db.Model):
    __tablename__ = "pengaduan"

    id_pengaduan = db.Column(db.Integer, primary_key=True)

    # Murid terkait. Untuk laporan orang tua tetap menunjuk anak; untuk guru NULL.
    id_murid = db.Column(
        db.Integer,
        db.ForeignKey("murid.id_murid"),
        nullable=True,
    )
    id_ortu = db.Column(
        db.Integer,
        db.ForeignKey("orang_tua.id_ortu"),
        nullable=True,
    )
    id_guru = db.Column(
        db.Integer,
        db.ForeignKey("guru.id_guru"),
        nullable=True,
    )

    tipe_pelapor = db.Column(
        db.Enum(
            "murid",
            "orang_tua",
            "guru",
            name="tipe_pelapor_pengaduan_enum",
        ),
        nullable=False,
        default="murid",
    )
    jenis_laporan = db.Column(
        db.Enum("pengaduan", "aspirasi", name="jenis_laporan_pengaduan_enum"),
        nullable=False,
        default="pengaduan",
    )
    mode_pelaporan = db.Column(
        db.Enum("terbuka", "rahasia", "anonim", name="mode_pelaporan_enum"),
        nullable=False,
    )

    # String digunakan agar kategori khusus guru bisa berkembang tanpa migrasi ENUM.
    kategori_pengaduan = db.Column(db.String(120), nullable=False)
    sub_kategori = db.Column(db.String(160), nullable=True)
    isi_pengaduan = db.Column(db.Text, nullable=False)

    tujuan_penanganan = db.Column(db.String(180), nullable=True)
    metadata_pelapor = db.Column(db.Text, nullable=True)
    lampiran = db.Column(db.String(255), nullable=True)

    status = db.Column(
        db.Enum(
            "menunggu",
            "dikirim",
            "ditinjau",
            "diproses",
            "menunggu_informasi",
            "selesai",
            "ditolak",
            name="status_pengaduan_enum",
        ),
        nullable=False,
        default="menunggu",
    )

    catatan_admin = db.Column(db.Text, nullable=True)
    tanggal_pengaduan = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    tanggal_ditindaklanjuti = db.Column(db.DateTime, nullable=True)

    murid = db.relationship("Murid", backref="pengaduan_list", lazy=True)

    def _get_orang_tua(self):
        if not self.id_ortu:
            return {}
        try:
            row = db.session.execute(
                text(
                    """
                    SELECT nama_ortu, no_hp
                    FROM orang_tua
                    WHERE id_ortu = :id_ortu
                    LIMIT 1
                    """
                ),
                {"id_ortu": self.id_ortu},
            ).mappings().first()
            return dict(row) if row else {}
        except Exception:
            return {}

    def _get_guru(self):
        if not self.id_guru:
            return {}
        try:
            row = db.session.execute(
                text(
                    """
                    SELECT nama_guru, nip
                    FROM guru
                    WHERE id_guru = :id_guru
                    LIMIT 1
                    """
                ),
                {"id_guru": self.id_guru},
            ).mappings().first()
            return dict(row) if row else {}
        except Exception:
            return {}

    def _metadata_dict(self):
        if not self.metadata_pelapor:
            return {}
        try:
            value = json.loads(self.metadata_pelapor)
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    def to_dict(self):
        nama_murid = self.murid.nama_murid if self.murid else None
        nis = self.murid.nis if self.murid else None
        id_kelas = self.murid.id_kelas if self.murid else None
        nama_kelas = (
            self.murid.kelas.nama_kelas
            if self.murid and self.murid.kelas
            else None
        )
        tingkat = (
            self.murid.kelas.tingkat.pangkat
            if self.murid
            and self.murid.kelas
            and getattr(self.murid.kelas, "tingkat", None)
            else None
        )

        ortu = self._get_orang_tua()
        guru = self._get_guru()
        nama_ortu = ortu.get("nama_ortu")
        nomor_telepon = ortu.get("no_hp")
        nama_guru = guru.get("nama_guru")
        nip = guru.get("nip")

        if self.tipe_pelapor == "orang_tua":
            pelapor_display = (
                f"Orang tua dari {nama_murid}" if nama_murid else "Orang tua"
            )
        elif self.tipe_pelapor == "guru":
            pelapor_display = nama_guru or "Guru"
        else:
            pelapor_display = nama_murid or "Murid"

        return {
            "id_pengaduan": self.id_pengaduan,
            "id_murid": self.id_murid,
            "id_ortu": self.id_ortu,
            "id_guru": self.id_guru,
            "tipe_pelapor": self.tipe_pelapor,
            "jenis_laporan": self.jenis_laporan,
            "pelapor_display": pelapor_display,
            "nama_ortu": nama_ortu,
            "nomor_telepon": nomor_telepon,
            "no_hp": nomor_telepon,
            "nama_guru": nama_guru,
            "nip": nip,
            "nama_murid": nama_murid,
            "nis": nis,
            "id_kelas": id_kelas,
            "nama_kelas": nama_kelas,
            "tingkat": tingkat,
            "mode_pelaporan": self.mode_pelaporan,
            "kategori_pengaduan": self.kategori_pengaduan,
            "sub_kategori": self.sub_kategori,
            "isi_pengaduan": self.isi_pengaduan,
            "tujuan_penanganan": self.tujuan_penanganan,
            "metadata_pelapor": self._metadata_dict(),
            "lampiran": self.lampiran,
            "status": self.status,
            "catatan_admin": self.catatan_admin,
            "tanggal_pengaduan": (
                self.tanggal_pengaduan.strftime("%Y-%m-%d %H:%M:%S")
                if self.tanggal_pengaduan
                else None
            ),
            "tanggal_ditindaklanjuti": (
                self.tanggal_ditindaklanjuti.strftime("%Y-%m-%d %H:%M:%S")
                if self.tanggal_ditindaklanjuti
                else None
            ),
        }
