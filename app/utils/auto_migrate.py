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
