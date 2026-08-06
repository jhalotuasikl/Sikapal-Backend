from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

def _column_exists(db, table: str, column: str) -> bool:
    try:
        sql = text("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND COLUMN_NAME = :c
        """)
        cnt = db.session.execute(sql, {"t": table, "c": column}).scalar() or 0
        return int(cnt) > 0
    except Exception:
        # Jika info_schema tidak bisa diakses, anggap tidak ada.
        return False


def _column_type(db, table: str, column: str) -> str:
    try:
        sql = text("""
            SELECT COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND COLUMN_NAME = :c
            LIMIT 1
        """)
        return str(db.session.execute(sql, {"t": table, "c": column}).scalar() or "")
    except Exception:
        return ""

def _column_nullable(db, table: str, column: str) -> bool:
    try:
        sql = text("""
            SELECT IS_NULLABLE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND COLUMN_NAME = :c
            LIMIT 1
        """)
        value = db.session.execute(sql, {"t": table, "c": column}).scalar()
        return str(value or "").upper() == "YES"
    except Exception:
        return False

def ensure_schema(db):
    """Auto-fix schema kecil supaya backend tidak crash saat kolom belum ada."""
    try:
        # nilai.status_kirim (dipakai untuk fitur 'kirim ke admin')
        if not _column_exists(db, "nilai", "status_kirim"):
            db.session.execute(text("""
                ALTER TABLE nilai
                ADD COLUMN status_kirim TINYINT(1) NOT NULL DEFAULT 0
            """))
            db.session.commit()

        # kehadiran_guru.instruksi (instruksi saat guru izin/sakit)
        if not _column_exists(db, "kehadiran_guru", "instruksi"):
            db.session.execute(text("""
                ALTER TABLE kehadiran_guru
                ADD COLUMN instruksi TEXT NULL AFTER alasan
            """))
            db.session.commit()


        # pengaduan.sub_kategori (pilihan dinamis berdasarkan jenis dan kategori)
        if not _column_exists(db, "pengaduan", "sub_kategori"):
            db.session.execute(text("""
                ALTER TABLE pengaduan
                ADD COLUMN sub_kategori VARCHAR(160) NULL
                AFTER kategori_pengaduan
            """))
            db.session.commit()

        # Pengaduan guru dan alur tindak lanjut yang lebih lengkap.
        if not _column_exists(db, "pengaduan", "id_guru"):
            db.session.execute(text("""
                ALTER TABLE pengaduan
                ADD COLUMN id_guru INT NULL AFTER id_ortu
            """))
            db.session.commit()

        for column_name, ddl in {
            "tujuan_penanganan": "VARCHAR(180) NULL",
            "metadata_pelapor": "TEXT NULL",
            "lampiran": "VARCHAR(255) NULL",
        }.items():
            if not _column_exists(db, "pengaduan", column_name):
                db.session.execute(text(
                    f"ALTER TABLE pengaduan ADD COLUMN {column_name} {ddl}"
                ))
                db.session.commit()

        id_murid_type = _column_type(db, "pengaduan", "id_murid").lower()
        if id_murid_type and not _column_nullable(db, "pengaduan", "id_murid"):
            db.session.execute(text("""
                ALTER TABLE pengaduan
                MODIFY COLUMN id_murid INT NULL
            """))
            db.session.commit()

        tipe_type = _column_type(db, "pengaduan", "tipe_pelapor").lower()
        if tipe_type and "guru" not in tipe_type:
            db.session.execute(text("""
                ALTER TABLE pengaduan
                MODIFY COLUMN tipe_pelapor
                ENUM('murid','orang_tua','guru') NOT NULL DEFAULT 'murid'
            """))
            db.session.commit()

        kategori_type = _column_type(db, "pengaduan", "kategori_pengaduan").lower()
        if kategori_type.startswith("enum"):
            db.session.execute(text("""
                ALTER TABLE pengaduan
                MODIFY COLUMN kategori_pengaduan VARCHAR(120) NOT NULL
            """))
            db.session.commit()

        pengaduan_status_type = _column_type(db, "pengaduan", "status").lower()
        if pengaduan_status_type and "menunggu_informasi" not in pengaduan_status_type:
            db.session.execute(text("""
                ALTER TABLE pengaduan
                MODIFY COLUMN status
                ENUM('menunggu','dikirim','ditinjau','diproses',
                     'menunggu_informasi','selesai','ditolak')
                NOT NULL DEFAULT 'menunggu'
            """))
            db.session.commit()

        # murid_tingkat.status harus mendukung status riwayat tinggal kelas.
        # Perubahan hanya dijalankan pada schema lama yang enum-nya belum lengkap.
        status_type = _column_type(db, "murid_tingkat", "status").lower()
        if status_type and "tinggal_kelas" not in status_type:
            db.session.execute(text("""
                ALTER TABLE murid_tingkat
                MODIFY COLUMN status
                ENUM('aktif','selesai','lulus','pindah','tinggal_kelas')
                NULL DEFAULT 'aktif'
            """))
            db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
    except Exception:
        db.session.rollback()
