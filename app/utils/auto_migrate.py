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
    except SQLAlchemyError:
        db.session.rollback()
    except Exception:
        db.session.rollback()
