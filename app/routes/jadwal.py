# app/routes/jadwal.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.jadwal import Jadwal
from app.models.kelas import Kelas
from app.models.mata_pelajaran import MataPelajaran
from app.models.jadwal_guru import JadwalGuru
from app.models.jadwal_murid import jadwal_murid
from app.models.guru import Guru
from app.models.murid import Murid
from app.models.tingkat import Tingkat
from app.models.murid_tingkat import MuridTingkat
from app.models.kehadiran_murid import KehadiranMurid
from app.models.kehadiran_guru import KehadiranGuru
from app.models.nilai import Nilai
from app.models.monitoring import LaporanMonitoring
from app.models.kuisoner import Kuisoner
from app.models.murid_mapel import MuridMapel
from app.models.kelas_mapel import kelas_mapel

jadwal_bp = Blueprint("jadwal", __name__)


# =========================
# helper: timezone aplikasi
# =========================
# Atur dari .env:
# APP_TIMEZONE=Asia/Jakarta   -> WIB
# APP_TIMEZONE=Asia/Makassar  -> WITA
# APP_TIMEZONE=Asia/Jayapura  -> WIT
_DEFAULT_APP_TIMEZONE = "Asia/Jakarta"


def _app_timezone():
    tz_name = os.getenv("APP_TIMEZONE", _DEFAULT_APP_TIMEZONE).strip() or _DEFAULT_APP_TIMEZONE
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(_DEFAULT_APP_TIMEZONE)


def _now_app():
    return datetime.now(_app_timezone())


# =========================
# helper: hari Indonesia
# =========================
HARI_VALID = {
    "senin": "Senin",
    "selasa": "Selasa",
    "rabu": "Rabu",
    "kamis": "Kamis",
    "jumat": "Jumat",
    "jum\'at": "Jumat",
    "jumat\'": "Jumat",
    "jum’at": "Jumat",
    "sabtu": "Sabtu",
    "minggu": "Minggu",
}


def normalisasi_hari(value):
    if value is None:
        return None

    text = str(value).strip().lower()
    text = text.replace("’", "'")

    # Samakan variasi Jumat
    if text in ["jum'at", "jumat'", "jum’at", "jumat"]:
        text = "jumat"

    return HARI_VALID.get(text)


def hari_ini_indonesia():
    now_app = _now_app()
    map_hari = {
        "monday": "Senin",
        "tuesday": "Selasa",
        "wednesday": "Rabu",
        "thursday": "Kamis",
        "friday": "Jumat",
        "saturday": "Sabtu",
        "sunday": "Minggu",
    }
    return map_hari[now_app.strftime("%A").lower()]


def filter_hari(query, hari):
    hari_normal = normalisasi_hari(hari)
    if not hari_normal:
        return query

    # Lower + trim supaya data lama seperti "Rabu", "rabu", atau " Minggu " tetap terbaca.
    return query.filter(func.lower(func.trim(Jadwal.hari)) == hari_normal.lower())


def label_hari(value):
    return normalisasi_hari(value) or str(value or "-")




_STATUS_TIDAK_AKTIF = [
    "selesai", "arsip", "diarsipkan", "archive", "archived",
    "nonaktif", "non aktif", "non-aktif", "inactive",
]


def _status_belum_selesai_expr(column):
    """Status NULL/kosong dianggap aktif; status selesai/arsip/nonaktif tidak ditampilkan."""
    return ~func.lower(func.trim(func.coalesce(column, "aktif"))).in_(_STATUS_TIDAK_AKTIF)


def _status_obj_aktif(obj):
    return str(getattr(obj, "status", None) or "aktif").strip().lower() == "aktif"


def _jadwal_kelas_aktif_obj(jadwal):
    if not jadwal or not _status_obj_aktif(jadwal):
        return False
    kelas = getattr(jadwal, "kelas", None) or Kelas.query.get(getattr(jadwal, "id_kelas", None))
    return kelas is None or _status_obj_aktif(kelas)


def _jadwal_kelas_belum_selesai_expr():
    return db.and_(
        _status_belum_selesai_expr(Jadwal.status),
        _status_belum_selesai_expr(Kelas.status),
    )

HARI_ORDER_INDEX = {
    "senin": 1,
    "selasa": 2,
    "rabu": 3,
    "kamis": 4,
    "jumat": 5,
    "jum'at": 5,
    "sabtu": 6,
    "minggu": 7,
}


def hari_order_value(value):
    text = str(value or "").strip().lower().replace("’", "'")
    return HARI_ORDER_INDEX.get(text, 99)


def jadwal_sort_key_from_tuple(row):
    j = row[0]
    k = row[1] if len(row) > 1 else None
    t = row[3] if len(row) > 3 else None
    return (
        getattr(t, "pangkat", 0) if t is not None else 0,
        getattr(k, "nama_kelas", "") if k is not None else "",
        hari_order_value(getattr(j, "hari", None)),
        str(getattr(j, "jam_mulai", "") or ""),
        getattr(j, "id_jadwal", 0) or 0,
    )


def _murid_aktif_di_kelas(id_kelas):
    murid = (
        db.session.query(Murid)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .filter(
            MuridTingkat.id_kelas == id_kelas,
            MuridTingkat.status == "aktif",
        )
        .order_by(Murid.nama_murid.asc())
        .all()
    )
    if murid:
        return murid
    return Murid.query.filter_by(id_kelas=id_kelas).order_by(Murid.nama_murid.asc()).all()


# =========================
# helper: cek jadwal milik guru login
# =========================
def jadwal_milik_guru(id_jadwal: int, id_guru: int) -> bool:
    return db.session.query(JadwalGuru).filter_by(
        id_jadwal=id_jadwal,
        id_guru=id_guru
    ).first() is not None



def parse_jam_value(value):
    if value is None:
        return None

    if hasattr(value, "hour") and hasattr(value, "minute"):
        return value

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except Exception:
            pass

    return None


def time_to_minutes(value):
    if value is None:
        return None
    return int(value.hour) * 60 + int(value.minute)


def jadwal_has_min_gap(jam_mulai_a, jam_selesai_a, jam_mulai_b, jam_selesai_b, min_gap=10):
    """True jika dua rentang waktu tidak bentrok dan jaraknya minimal min_gap menit."""
    start_a = time_to_minutes(jam_mulai_a)
    end_a = time_to_minutes(jam_selesai_a)
    start_b = time_to_minutes(jam_mulai_b)
    end_b = time_to_minutes(jam_selesai_b)

    if None in [start_a, end_a, start_b, end_b]:
        return True

    return end_a + min_gap <= start_b or end_b + min_gap <= start_a


def jadwal_conflict_or_gap_too_close(jam_mulai_a, jam_selesai_a, jam_mulai_b, jam_selesai_b, min_gap=10):
    return not jadwal_has_min_gap(
        jam_mulai_a,
        jam_selesai_a,
        jam_mulai_b,
        jam_selesai_b,
        min_gap=min_gap,
    )


def get_jadwal_group(jadwal, status="aktif"):
    query = Jadwal.query.filter(
        Jadwal.id_kelas == jadwal.id_kelas,
        Jadwal.id_mapel == jadwal.id_mapel,
    )

    if status and status != "all":
        query = query.filter(Jadwal.status == status)

    data = query.all()
    return sorted(
        data,
        key=lambda row: (
            hari_order_value(row.hari),
            row.jam_mulai.strftime("%H:%M") if row.jam_mulai else "",
            row.id_jadwal or 0,
        ),
    )


def serialize_jadwal_row(jadwal, urutan=None):
    data = {
        "id_jadwal": jadwal.id_jadwal,
        "id_kelas": jadwal.id_kelas,
        "id_mapel": jadwal.id_mapel,
        "hari": label_hari(jadwal.hari),
        "jam_mulai": jadwal.jam_mulai.strftime("%H:%M") if jadwal.jam_mulai else None,
        "jam_selesai": jadwal.jam_selesai.strftime("%H:%M") if jadwal.jam_selesai else None,
        "status": getattr(jadwal, "status", "aktif"),
    }
    if urutan is not None:
        data["urutan"] = urutan
        data["kode"] = f"J{urutan}"
    return data


def format_jadwal_group(group):
    return ", ".join(
        f"J{idx}: {label_hari(j.hari)} {j.jam_mulai.strftime('%H:%M') if j.jam_mulai else '--:--'}-"
        f"{j.jam_selesai.strftime('%H:%M') if j.jam_selesai else '--:--'}"
        for idx, j in enumerate(group, start=1)
    )


def validate_guru_bentrok(id_guru, jadwal_group, exclude_jadwal_ids=None):
    exclude_jadwal_ids = set(exclude_jadwal_ids or [])
    target_ids = {j.id_jadwal for j in jadwal_group if j.id_jadwal}
    exclude_jadwal_ids.update(target_ids)

    jadwal_lama = (
        db.session.query(Jadwal)
        .join(JadwalGuru, Jadwal.id_jadwal == JadwalGuru.id_jadwal)
        .filter(
            JadwalGuru.id_guru == id_guru,
            Jadwal.status == "aktif",
            ~Jadwal.id_jadwal.in_(exclude_jadwal_ids) if exclude_jadwal_ids else True,
        )
        .all()
    )

    for target in jadwal_group:
        target_hari = label_hari(target.hari).lower()
        for lama in jadwal_lama:
            if label_hari(lama.hari).lower() != target_hari:
                continue

            if jadwal_conflict_or_gap_too_close(
                target.jam_mulai,
                target.jam_selesai,
                lama.jam_mulai,
                lama.jam_selesai,
                min_gap=10,
            ):
                return {
                    "message": "Guru yang dipilih mempunyai jadwal diwaktu yang sama, jarak antara waktu selesai dan mulai minimal 10 menit. Mohon pilih guru yang lain atau edit jam pada jadwal",
                    "detail": {
                        "jadwal_dipilih": serialize_jadwal_row(target),
                        "jadwal_bentrok": serialize_jadwal_row(lama),
                    },
                }

    return None


def validate_kelas_jadwal_bentrok(id_kelas, jadwal_baru, exclude_jadwal_ids=None):
    exclude_jadwal_ids = set(exclude_jadwal_ids or [])

    # Cek antar input baru dulu.
    for i in range(len(jadwal_baru)):
        for j in range(i + 1, len(jadwal_baru)):
            a = jadwal_baru[i]
            b = jadwal_baru[j]
            if label_hari(a["hari"]).lower() != label_hari(b["hari"]).lower():
                continue
            if jadwal_conflict_or_gap_too_close(
                a["jam_mulai"], a["jam_selesai"], b["jam_mulai"], b["jam_selesai"], min_gap=0
            ):
                return {
                    "message": f"Jadwal J{i + 1} dan J{j + 1} bentrok pada hari dan jam yang sama"
                }

    for idx, row in enumerate(jadwal_baru, start=1):
        q = Jadwal.query.filter(
            Jadwal.id_kelas == id_kelas,
            Jadwal.status == "aktif",
            func.lower(func.trim(Jadwal.hari)) == label_hari(row["hari"]).lower(),
        )
        if exclude_jadwal_ids:
            q = q.filter(~Jadwal.id_jadwal.in_(exclude_jadwal_ids))

        for lama in q.all():
            if jadwal_conflict_or_gap_too_close(
                row["jam_mulai"],
                row["jam_selesai"],
                lama.jam_mulai,
                lama.jam_selesai,
                min_gap=0,
            ):
                return {
                    "message": f"Jadwal J{idx} bentrok dengan jadwal lain pada kelas dan hari yang sama",
                    "detail": {
                        "jadwal_baru": {
                            "hari": row["hari"],
                            "jam_mulai": row["jam_mulai"].strftime("%H:%M"),
                            "jam_selesai": row["jam_selesai"].strftime("%H:%M"),
                        },
                        "jadwal_lama": serialize_jadwal_row(lama),
                    },
                }

    return None


def get_mapel_context(jadwal):
    row = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(Jadwal.id_jadwal == jadwal.id_jadwal)
        .first()
    )
    return row


# =====================================================
# LIST JADWAL (FILTER) - ADMIN (opsional)
# =====================================================
@jadwal_bp.route("/jadwal", methods=["GET"])
@jwt_required()
def list_jadwal():
    claims = get_jwt()
    role = claims.get("role")

    id_kelas = request.args.get("id_kelas")
    hari = request.args.get("hari")
    id_tingkat = request.args.get("id_tingkat")
    status = (request.args.get("status") or "aktif").lower().strip()

    query = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
    )

    if status != "all":
        query = query.filter(Kelas.status == status, Jadwal.status == status)

    if id_kelas:
        query = query.filter(Jadwal.id_kelas == id_kelas)

    if id_tingkat:
        query = query.filter(Kelas.id_tingkat == id_tingkat)

    if hari:
        hari_normal = normalisasi_hari(hari)
        if not hari_normal:
            return jsonify({"message": "Hari tidak valid"}), 400
        query = filter_hari(query, hari_normal)

    data = sorted(query.all(), key=jadwal_sort_key_from_tuple)

    return jsonify([
        {
            "id_jadwal": j.id_jadwal,
            "id_kelas": j.id_kelas,
            "id_mapel": j.id_mapel,
            "id_tingkat": t.id_tingkat,
            "tingkat": t.pangkat,
            "pangkat": t.pangkat,
            "nama_kelas": k.nama_kelas,
            "kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "tahun": k.tahun_ajaran,
            "status_kelas": getattr(k, "status", "aktif"),
            "status_jadwal": getattr(j, "status", "aktif"),
            "nama_mapel": m.nama_mapel,
            "mapel": m.nama_mapel,
            "hari": label_hari(j.hari),
            "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
            "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
            "status": getattr(j, "status", "aktif"),
            "status_kelas": getattr(k, "status", "aktif"),
        } for j, k, m, t in data
    ]), 200


# =====================================================
# DETAIL
# =====================================================
@jadwal_bp.route("/jadwal/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def detail_jadwal(id_jadwal):
    row = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(Jadwal.id_jadwal == id_jadwal)
        .first()
    )

    if not row:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404

    j, k, m, t = row

    group = get_jadwal_group(j)

    return jsonify({
        "id_jadwal": j.id_jadwal,
        "id_kelas": j.id_kelas,
        "id_mapel": j.id_mapel,
        "id_tingkat": t.id_tingkat,
        "tingkat": t.pangkat,
        "pangkat": t.pangkat,
        "nama_kelas": k.nama_kelas,
        "kelas": k.nama_kelas,
        "tahun_ajaran": k.tahun_ajaran,
        "tahun": k.tahun_ajaran,
        "nama_mapel": m.nama_mapel,
        "mapel": m.nama_mapel,
        "hari": label_hari(j.hari),
        "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
        "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
        "status": getattr(j, "status", "aktif"),
        "status_kelas": getattr(k, "status", "aktif"),
        "jumlah_jadwal": len(group),
        "id_jadwal_list": [row.id_jadwal for row in group],
        "jadwal_group": [serialize_jadwal_row(row, idx) for idx, row in enumerate(group, start=1)],
        "jadwal_text": format_jadwal_group(group),
    }), 200


# =====================================================
# CREATE (ADMIN ONLY)
# =====================================================
@jadwal_bp.route("/jadwal", methods=["POST"])
@jwt_required()
def create_jadwal():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    data = request.json or {}

    wajib = ["id_kelas", "id_mapel", "hari", "jam_mulai", "jam_selesai"]
    for f in wajib:
        if not data.get(f):
            return jsonify({"message": f"{f} wajib"}), 400

    hari_normal = normalisasi_hari(data.get("hari"))
    if not hari_normal:
        return jsonify({
            "message": "Hari tidak valid. Gunakan Senin, Selasa, Rabu, Kamis, Jumat, Sabtu, atau Minggu"
        }), 400

    # parse jam
    try:
        jam_mulai = datetime.strptime(data["jam_mulai"], "%H:%M").time()
        jam_selesai = datetime.strptime(data["jam_selesai"], "%H:%M").time()
    except:
        return jsonify({"message": "Format jam HH:MM"}), 400

    if jam_mulai >= jam_selesai:
        return jsonify({"message": "Jam tidak valid"}), 400

    kelas = Kelas.query.get(data["id_kelas"])
    mapel = MataPelajaran.query.get(data["id_mapel"])
    if not kelas or not mapel:
        return jsonify({"message": "Kelas / Mapel invalid"}), 400

    if getattr(kelas, "status", "aktif") != "aktif":
        return jsonify({"message": "Kelas sudah arsip, tidak bisa menambah jadwal baru"}), 400

    if mapel not in kelas.mapel:
        return jsonify({"message": "Mapel belum di kelas"}), 400

    jadwal = Jadwal(
        id_kelas=data["id_kelas"],
        id_mapel=data["id_mapel"],
        hari=hari_normal,
        jam_mulai=jam_mulai,
        jam_selesai=jam_selesai,
        status="aktif"
    )

    db.session.add(jadwal)
    db.session.commit()

    return jsonify({"message": "Jadwal dibuat", "id_jadwal": jadwal.id_jadwal}), 201


# =====================================================
# JADWAL HARI INI (GURU LOGIN) - FIX hari Indonesia
# =====================================================
@jadwal_bp.route("/guru/jadwal-hari-ini", methods=["GET"])
@jwt_required()
def jadwal_hari_ini():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Khusus guru"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "ID guru tidak ditemukan"}), 400

    hari_ini = hari_ini_indonesia()

    data = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(JadwalGuru, Jadwal.id_jadwal == JadwalGuru.id_jadwal)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(
            JadwalGuru.id_guru == id_guru,
            func.lower(func.trim(Jadwal.hari)) == hari_ini.lower(),
            _jadwal_kelas_belum_selesai_expr(),
        )
        .order_by(Jadwal.jam_mulai)
        .all()
    )

    return jsonify([
        {
            "id_jadwal": j.id_jadwal,
            "id_kelas": j.id_kelas,
            "id_mapel": j.id_mapel,
            "id_tingkat": t.id_tingkat,
            "tingkat": t.pangkat,
            "pangkat": t.pangkat,
            "hari": label_hari(j.hari),
            "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
            "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
            "nama_kelas": k.nama_kelas,
            "kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "tahun": k.tahun_ajaran,
            "status_kelas": getattr(k, "status", "aktif"),
            "status_jadwal": getattr(j, "status", "aktif"),
            "nama_mapel": m.nama_mapel,
            "mapel": m.nama_mapel,
        } for j, k, m, t in data
    ]), 200




# =====================================================
# JADWAL HARI INI (ADMIN) - SEMUA JADWAL AKTIF HARI INI
# =====================================================
@jadwal_bp.route("/admin/jadwal-hari-ini", methods=["GET"])
@jwt_required()
def jadwal_hari_ini_admin():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Khusus admin"}), 403

    hari_ini = hari_ini_indonesia()

    data = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(
            func.lower(func.trim(Jadwal.hari)) == hari_ini.lower(),
            _jadwal_kelas_belum_selesai_expr(),
        )
        .order_by(Jadwal.jam_mulai.asc(), Kelas.nama_kelas.asc(), MataPelajaran.nama_mapel.asc())
        .all()
    )

    result = []

    for j, k, m, t in data:
        guru_list = []
        try:
            guru_list = [jg.guru for jg in j.jadwal_guru] if j.jadwal_guru else []
        except Exception:
            guru_list = []

        nama_guru = ", ".join([g.nama_guru for g in guru_list if g]) if guru_list else "-"

        result.append({
            "id_jadwal": j.id_jadwal,
            "id_kelas": j.id_kelas,
            "id_mapel": j.id_mapel,
            "id_tingkat": t.id_tingkat,
            "tingkat": t.pangkat,
            "pangkat": t.pangkat,
            "hari": label_hari(j.hari),
            "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
            "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
            "nama_kelas": k.nama_kelas,
            "kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "tahun": k.tahun_ajaran,
            "status_kelas": getattr(k, "status", "aktif"),
            "status_jadwal": getattr(j, "status", "aktif"),
            "nama_mapel": m.nama_mapel,
            "mapel": m.nama_mapel,
            "guru": nama_guru,
        })

    return jsonify(result), 200


# =====================================================
# JADWAL GURU (SEMUA) - sudah benar (pakai jadwal_guru)
# =====================================================
@jadwal_bp.route("/guru/jadwal", methods=["GET"])
@jwt_required()
def get_jadwal_guru():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Khusus guru"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "ID guru tidak ditemukan"}), 400

    id_tingkat = request.args.get("id_tingkat")

    query = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(JadwalGuru, Jadwal.id_jadwal == JadwalGuru.id_jadwal)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(
            JadwalGuru.id_guru == id_guru,
            _jadwal_kelas_belum_selesai_expr(),
        )
    )

    if id_tingkat:
        query = query.filter(Kelas.id_tingkat == id_tingkat)

    data = sorted(query.all(), key=jadwal_sort_key_from_tuple)

    return jsonify([
        {
            "id_jadwal": j.id_jadwal,
            "id_kelas": j.id_kelas,
            "id_mapel": j.id_mapel,
            "id_tingkat": t.id_tingkat,
            "tingkat": t.pangkat,
            "pangkat": t.pangkat,
            "hari": label_hari(j.hari),
            "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
            "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
            "nama_kelas": k.nama_kelas,
            "kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "tahun": k.tahun_ajaran,
            "status_kelas": getattr(k, "status", "aktif"),
            "status_jadwal": getattr(j, "status", "aktif"),
            "nama_mapel": m.nama_mapel,
            "mapel": m.nama_mapel,
        } for j, k, m, t in data
    ]), 200


# =====================================================
# ✅ MURID BY JADWAL (INI YANG DIPAKAI FLUTTER)
# =====================================================
@jadwal_bp.route("/guru/jadwal/<int:id_jadwal>/murid", methods=["GET"])
@jwt_required()
def get_murid_by_jadwal(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Khusus guru"}), 403

    id_guru = claims.get("id_guru")

    # validasi jadwal milik guru (via jadwal_guru)
    from app.models.jadwal_guru import JadwalGuru
    cek = JadwalGuru.query.filter_by(id_jadwal=id_jadwal, id_guru=id_guru).first()
    if not cek:
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if not _jadwal_kelas_aktif_obj(jadwal):
        return jsonify({"message": "Jadwal sudah arsip"}), 403

    murid = _murid_aktif_di_kelas(jadwal.id_kelas)

    return jsonify([
        {"id_murid": m.id_murid, "nama_murid": m.nama_murid, "nis": m.nis}
        for m in murid
    ]), 200


@jadwal_bp.route("/guru/jadwal/<int:id_jadwal>/murid/jumlah", methods=["GET"])
@jwt_required()
def get_jumlah_murid_by_jadwal(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Khusus guru"}), 403

    id_guru = claims.get("id_guru")
    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if not _jadwal_kelas_aktif_obj(jadwal):
        return jsonify({
            "id_jadwal": id_jadwal,
            "id_kelas": getattr(jadwal, "id_kelas", None),
            "jumlah_murid": 0,
            "jumlah": 0,
        }), 200

    jumlah_murid = len(_murid_aktif_di_kelas(jadwal.id_kelas))

    return jsonify({
        "id_jadwal": id_jadwal,
        "id_kelas": jadwal.id_kelas,
        "jumlah_murid": jumlah_murid,
        "jumlah": jumlah_murid,
    }), 200


# =====================================================
# GET JADWAL PER KELAS (ADMIN/GURU/MURID)
# Dipakai DetailKelasPage -> KelasService.getJadwalKelas()
# =====================================================
@jadwal_bp.route("/jadwal/kelas/<int:id_kelas>", methods=["GET"])
@jwt_required()
def jadwal_by_kelas(id_kelas):
    claims = get_jwt()
    status = (request.args.get("status") or "aktif").lower().strip()

    if claims.get("role") not in ["admin", "guru", "murid"]:
        return jsonify({"message": "Akses ditolak"}), 403

    data_query = (
        db.session.query(Jadwal, Kelas, MataPelajaran, Tingkat)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(Jadwal.id_kelas == id_kelas)
    )

    if status != "all":
        data_query = data_query.filter(Jadwal.status == status, Kelas.status == status)

    data = sorted(data_query.all(), key=jadwal_sort_key_from_tuple)

    result = []

    for j, k, m, t in data:
        # ambil semua guru yang di-assign ke jadwal ini (bisa kosong)
        guru_list = [jg.guru for jg in j.jadwal_guru] if j.jadwal_guru else []
        guru_names = ", ".join([g.nama_guru for g in guru_list]) if guru_list else None
        guru_ids = [g.id_guru for g in guru_list] if guru_list else []

        result.append({
            "id_jadwal": j.id_jadwal,
            "id_kelas": j.id_kelas,
            "id_mapel": j.id_mapel,
            "id_tingkat": t.id_tingkat,
            "tingkat": t.pangkat,
            "pangkat": t.pangkat,
            "nama_kelas": k.nama_kelas,
            "kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "tahun": k.tahun_ajaran,
            "nama_mapel": m.nama_mapel if m else None,
            "mapel": m.nama_mapel if m else None,
            "hari": label_hari(j.hari),
            "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
            "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,

            # guru bisa lebih dari 1
            "nama_guru": guru_names,
            "guru_ids": guru_ids,
            "status": getattr(j, "status", "aktif"),
            "status_kelas": getattr(k, "status", "aktif"),
        })

    return jsonify(result), 200


# =====================================================
# ADMIN: ASSIGN GURU KE JADWAL (OTOMATIS 1 GRUP MAPEL)
# Endpoint: POST /api/admin/jadwal/<id_jadwal>/guru
# Body: { "id_guru": 1 }
# =====================================================
@jadwal_bp.route("/admin/jadwal/<int:id_jadwal>/guru", methods=["POST"])
@jwt_required()
def admin_assign_guru_to_jadwal(id_jadwal):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    data = request.json or {}
    id_guru = data.get("id_guru")

    if not id_guru:
        return jsonify({"message": "id_guru wajib"}), 400

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    guru = Guru.query.get_or_404(id_guru)

    if getattr(jadwal, "status", "aktif") != "aktif":
        return jsonify({"message": "Jadwal sudah tidak aktif"}), 400

    jadwal_group = get_jadwal_group(jadwal)
    if not jadwal_group:
        return jsonify({"message": "Grup jadwal tidak ditemukan"}), 404

    bentrok = validate_guru_bentrok(id_guru, jadwal_group)
    if bentrok:
        return jsonify(bentrok), 409

    dibuat = []
    sudah_ada = []

    try:
        for row in jadwal_group:
            exist = JadwalGuru.query.filter_by(
                id_jadwal=row.id_jadwal,
                id_guru=id_guru,
            ).first()

            if exist:
                sudah_ada.append(row.id_jadwal)
                continue

            link = JadwalGuru(id_jadwal=row.id_jadwal, id_guru=id_guru)
            db.session.add(link)
            dibuat.append(row.id_jadwal)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": "Gagal assign guru ke jadwal",
            "error": str(e),
        }), 500

    status_code = 201 if dibuat else 200
    return jsonify({
        "message": "Guru berhasil di-assign otomatis ke semua jadwal mapel ini" if dibuat else "Guru sudah ter-assign pada semua jadwal mapel ini",
        "id_jadwal": id_jadwal,
        "id_jadwal_list": [row.id_jadwal for row in jadwal_group],
        "id_jadwal_ditambahkan": dibuat,
        "id_jadwal_sudah_ada": sudah_ada,
        "jumlah_jadwal": len(jadwal_group),
        "id_guru": id_guru,
        "nama_guru": guru.nama_guru,
        "nip": guru.nip,
    }), status_code


# =====================================================
# ADMIN: UNASSIGN GURU DARI JADWAL (OTOMATIS 1 GRUP MAPEL)
# Endpoint: DELETE /api/admin/jadwal/<id_jadwal>/guru/<id_guru>
# =====================================================
@jadwal_bp.route("/admin/jadwal/<int:id_jadwal>/guru/<int:id_guru>", methods=["DELETE"])
@jwt_required()
def admin_unassign_guru_from_jadwal(id_jadwal, id_guru):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if not _jadwal_kelas_aktif_obj(jadwal):
        return jsonify([]), 200

    jadwal_group = get_jadwal_group(jadwal)
    id_jadwal_group = [row.id_jadwal for row in jadwal_group]

    links = JadwalGuru.query.filter(
        JadwalGuru.id_guru == id_guru,
        JadwalGuru.id_jadwal.in_(id_jadwal_group),
    ).all()

    if not links:
        return jsonify({"message": "Relasi tidak ada"}), 404

    for link in links:
        db.session.delete(link)

    db.session.commit()

    return jsonify({
        "message": "Guru dihapus dari semua jadwal mapel ini",
        "id_jadwal_list": id_jadwal_group,
        "jumlah_dihapus": len(links),
    }), 200


@jadwal_bp.route("/admin/jadwal/<int:id_jadwal>/guru", methods=["GET"])
@jwt_required()
def admin_get_guru_jadwal(id_jadwal):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if not _jadwal_kelas_aktif_obj(jadwal):
        return jsonify([]), 200

    jadwal_group = get_jadwal_group(jadwal)
    id_jadwal_group = [row.id_jadwal for row in jadwal_group]

    data = (
        db.session.query(Guru)
        .join(JadwalGuru, Guru.id_guru == JadwalGuru.id_guru)
        .filter(JadwalGuru.id_jadwal.in_(id_jadwal_group))
        .distinct()
        .order_by(Guru.nama_guru.asc())
        .all()
    )

    return jsonify([
        {
            "id_guru": g.id_guru,
            "nama_guru": g.nama_guru,
            "nip": g.nip,
        }
        for g in data
    ]), 200


# =====================================================
# ADMIN: EDIT JADWAL
# Endpoint single: PUT /api/admin/jadwal/<id_jadwal>
# Body single: {"hari":"Senin", "jam_mulai":"07:00", "jam_selesai":"08:30"}
# Body grup: {"jadwal_list":[{"id_jadwal":1,"hari":"Senin","jam_mulai":"07:00","jam_selesai":"08:30"}]}
# =====================================================
@jadwal_bp.route("/admin/jadwal/<int:id_jadwal>", methods=["PUT"])
@jwt_required()
def admin_update_jadwal(id_jadwal):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    jadwal_utama = Jadwal.query.get_or_404(id_jadwal)
    data = request.get_json(silent=True) or {}

    raw_list = data.get("jadwal_list") or data.get("jadwal") or data.get("jadwalList")
    if not isinstance(raw_list, list) or not raw_list:
        raw_list = [data]

    jadwal_group = get_jadwal_group(jadwal_utama)
    allowed_ids = {row.id_jadwal for row in jadwal_group}

    parsed_rows = []
    for idx, row in enumerate(raw_list, start=1):
        if not isinstance(row, dict):
            return jsonify({"message": f"Format jadwal J{idx} tidak valid"}), 400

        id_row = row.get("id_jadwal") or row.get("jadwal_id") or row.get("id") or id_jadwal
        try:
            id_row = int(id_row)
        except Exception:
            return jsonify({"message": f"ID jadwal J{idx} tidak valid"}), 400

        if id_row not in allowed_ids:
            return jsonify({
                "message": "Jadwal yang diedit harus berada pada mapel dan kelas yang sama"
            }), 400

        hari_normal = normalisasi_hari(row.get("hari"))
        jam_mulai = parse_jam_value(row.get("jam_mulai") or row.get("jamMulai"))
        jam_selesai = parse_jam_value(row.get("jam_selesai") or row.get("jamSelesai"))

        if not hari_normal or not jam_mulai or not jam_selesai:
            return jsonify({"message": f"Data jadwal J{idx} belum lengkap"}), 400

        if jam_mulai >= jam_selesai:
            return jsonify({"message": f"Jam selesai J{idx} harus lebih besar dari jam mulai"}), 400

        parsed_rows.append({
            "id_jadwal": id_row,
            "hari": hari_normal,
            "jam_mulai": jam_mulai,
            "jam_selesai": jam_selesai,
        })

    exclude_ids = {row["id_jadwal"] for row in parsed_rows}
    bentrok_kelas = validate_kelas_jadwal_bentrok(
        id_kelas=jadwal_utama.id_kelas,
        jadwal_baru=parsed_rows,
        exclude_jadwal_ids=exclude_ids,
    )
    if bentrok_kelas:
        return jsonify(bentrok_kelas), 409

    # Simulasi jadwal setelah diedit untuk validasi bentrok guru.
    simulasi_group = []
    perubahan_by_id = {row["id_jadwal"]: row for row in parsed_rows}
    for old in jadwal_group:
        row = perubahan_by_id.get(old.id_jadwal)
        if row:
            old.hari = row["hari"]
            old.jam_mulai = row["jam_mulai"]
            old.jam_selesai = row["jam_selesai"]
        simulasi_group.append(old)

    guru_ids = (
        db.session.query(JadwalGuru.id_guru)
        .filter(JadwalGuru.id_jadwal.in_([j.id_jadwal for j in jadwal_group]))
        .distinct()
        .all()
    )

    for (id_guru,) in guru_ids:
        bentrok_guru = validate_guru_bentrok(
            id_guru=id_guru,
            jadwal_group=simulasi_group,
            exclude_jadwal_ids=[j.id_jadwal for j in jadwal_group],
        )
        if bentrok_guru:
            db.session.rollback()
            return jsonify(bentrok_guru), 409

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": "Gagal mengubah jadwal",
            "error": str(e),
        }), 500

    jadwal_group_baru = get_jadwal_group(jadwal_utama)
    return jsonify({
        "message": "Jadwal berhasil diubah",
        "id_jadwal_list": [row.id_jadwal for row in jadwal_group_baru],
        "jadwal_group": [serialize_jadwal_row(row, idx) for idx, row in enumerate(jadwal_group_baru, start=1)],
    }), 200


# =====================================================
# ADMIN: HAPUS JADWAL
# Endpoint: DELETE /api/admin/jadwal/<id_jadwal>
# - Data absensi, nilai, monitoring, kuisoner, dan assignment ikut dihapus.
# - Relasi mapel-kelas hanya dilepas jika tidak ada jadwal aktif lain untuk
#   mapel yang sama pada kelas tersebut.
# =====================================================
@jadwal_bp.route("/admin/jadwal/<int:id_jadwal>", methods=["DELETE"])
@jwt_required()
def admin_delete_jadwal(id_jadwal):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    id_kelas = jadwal.id_kelas
    id_mapel = jadwal.id_mapel

    try:
        jumlah_jadwal_aktif_lain = Jadwal.query.filter(
            Jadwal.id_kelas == id_kelas,
            Jadwal.id_mapel == id_mapel,
            Jadwal.id_jadwal != id_jadwal,
            Jadwal.status == "aktif",
        ).count()

        deleted_kehadiran_murid = KehadiranMurid.query.filter_by(
            id_jadwal=id_jadwal
        ).delete(synchronize_session=False)
        deleted_nilai = Nilai.query.filter_by(
            id_jadwal=id_jadwal
        ).delete(synchronize_session=False)
        deleted_kehadiran_guru = KehadiranGuru.query.filter_by(
            id_jadwal=id_jadwal
        ).delete(synchronize_session=False)
        deleted_monitoring = LaporanMonitoring.query.filter_by(
            id_jadwal=id_jadwal
        ).delete(synchronize_session=False)

        kuisoner_rows = Kuisoner.query.filter_by(id_jadwal=id_jadwal).all()
        deleted_kuisoner = len(kuisoner_rows)
        for kuisoner in kuisoner_rows:
            db.session.delete(kuisoner)

        deleted_guru = JadwalGuru.query.filter_by(
            id_jadwal=id_jadwal
        ).delete(synchronize_session=False)

        deleted_murid = db.session.execute(
            jadwal_murid.delete().where(jadwal_murid.c.id_jadwal == id_jadwal)
        ).rowcount or 0

        mapel_dihapus_dari_kelas = jumlah_jadwal_aktif_lain == 0
        deleted_murid_mapel = 0

        if mapel_dihapus_dari_kelas and id_kelas and id_mapel:
            db.session.execute(
                kelas_mapel.delete().where(
                    kelas_mapel.c.id_kelas == id_kelas,
                    kelas_mapel.c.id_mapel == id_mapel,
                )
            )

            murid_ids = {
                row[0]
                for row in db.session.query(MuridTingkat.id_murid).filter(
                    MuridTingkat.id_kelas == id_kelas,
                    func.lower(func.trim(MuridTingkat.status)).in_(["aktif", "tinggal_kelas"]),
                ).all()
            }
            murid_ids.update(
                row[0]
                for row in db.session.query(Murid.id_murid).filter(
                    Murid.id_kelas == id_kelas,
                ).all()
            )

            if murid_ids:
                deleted_murid_mapel = MuridMapel.query.filter(
                    MuridMapel.id_mapel == id_mapel,
                    MuridMapel.id_murid.in_(murid_ids),
                ).delete(synchronize_session=False)

        db.session.delete(jadwal)
        db.session.commit()

        if mapel_dihapus_dari_kelas:
            message = "Jadwal terakhir dan mata pelajaran berhasil dihapus dari kelas"
        else:
            message = "Jadwal berhasil dihapus; mata pelajaran tetap tersedia karena masih memiliki jadwal lain"

        return jsonify({
            "message": message,
            "id_jadwal": id_jadwal,
            "id_kelas": id_kelas,
            "id_mapel": id_mapel,
            "mapel_dihapus_dari_kelas": mapel_dihapus_dari_kelas,
            "sisa_jadwal_aktif_mapel": jumlah_jadwal_aktif_lain,
            "data_terhapus": {
                "kehadiran_murid": deleted_kehadiran_murid,
                "nilai_murid": deleted_nilai,
                "kehadiran_guru": deleted_kehadiran_guru,
                "monitoring": deleted_monitoring,
                "kuisoner": deleted_kuisoner,
                "assignment_guru": deleted_guru,
                "assignment_murid": deleted_murid,
                "murid_mapel": deleted_murid_mapel,
            },
        }), 200

    except IntegrityError as e:
        db.session.rollback()
        return jsonify({
            "message": "Jadwal tidak dapat dihapus karena masih memiliki relasi data yang belum berhasil dibersihkan.",
            "error": str(e),
        }), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": "Gagal menghapus jadwal",
            "error": str(e),
        }), 500


@jadwal_bp.route("/admin/jadwal/<int:id_jadwal>/murid", methods=["GET"])
@jwt_required()
def admin_get_murid_by_jadwal(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if not _jadwal_kelas_aktif_obj(jadwal):
        return jsonify([]), 200

    murid = _murid_aktif_di_kelas(jadwal.id_kelas)

    return jsonify([
        {"id_murid": m.id_murid, "nama_murid": m.nama_murid, "nis": m.nis}
        for m in murid
    ]), 200


# =====================================================
# JADWAL HARI INI (MURID LOGIN) - REALTIME DASHBOARD
# =====================================================
@jadwal_bp.route("/murid/jadwal-hari-ini", methods=["GET"])
@jwt_required()
def jadwal_hari_ini_murid():
    claims = get_jwt()
    if claims.get("role") not in ["murid", "orang_tua"]:
        return jsonify({"message": "Khusus murid"}), 403

    id_murid = claims.get("id_murid")
    if not id_murid:
        return jsonify({"message": "ID murid tidak ditemukan"}), 400

    murid = Murid.query.get(id_murid)
    if not murid:
        return jsonify({"message": "Murid tidak ditemukan"}), 404

    if not murid.id_kelas:
        return jsonify([]), 200

    hari_ini = hari_ini_indonesia()

    data = (
        db.session.query(Jadwal, Kelas, MataPelajaran)
        .join(Kelas, Jadwal.id_kelas == Kelas.id_kelas)
        .join(MataPelajaran, Jadwal.id_mapel == MataPelajaran.id_mapel)
        .filter(
            Jadwal.id_kelas == murid.id_kelas,
            func.lower(func.trim(Jadwal.hari)) == hari_ini.lower(),
            _jadwal_kelas_belum_selesai_expr(),
        )
        .order_by(Jadwal.jam_mulai.asc())
        .all()
    )

    result = []

    for j, k, m in data:
        guru_list = [jg.guru for jg in j.jadwal_guru] if j.jadwal_guru else []
        nama_guru = ", ".join([g.nama_guru for g in guru_list]) if guru_list else "-"

        result.append({
            "id_jadwal": j.id_jadwal,
            "hari": label_hari(j.hari),
            "jam_mulai": j.jam_mulai.strftime("%H:%M"),
            "jam_selesai": j.jam_selesai.strftime("%H:%M"),
            "kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "tahun": k.tahun_ajaran,
            "mapel": m.nama_mapel,
            "guru": nama_guru,
        })

    return jsonify(result), 200
