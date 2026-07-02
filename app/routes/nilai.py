# app/routes/nilai.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.nilai import Nilai
from app.models.murid import Murid
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.kelas import Kelas
from app.models.mata_pelajaran import MataPelajaran
from app.models.guru import Guru
from app.models.murid_tingkat import MuridTingkat

nilai_bp = Blueprint("nilai", __name__)


def konversi_huruf(nilai):
    """
    Klasifikasi nilai sesuai standar instansi:
    86 - 100 = A
    66 - 85  = B
    41 - 65  = C
    0  - 40  = D
    """
    if nilai >= 86:
        return "A"
    if nilai >= 66:
        return "B"
    if nilai >= 41:
        return "C"
    return "D"


def normalisasi_semester(value):
    """
    Format produksi terbaru memakai ENUM/string: ganjil/genap.
    Tetap menerima input lama dari frontend: 1/2 atau semester 1/2.
    """
    text = str(value or "").strip().lower()
    if text in ["2", "genap", "semester 2", "semester genap"]:
        return "genap"
    return "ganjil"


def _semester_filter_values(value):
    """
    Agar data lama dan data baru tetap terbaca:
    - ganjil cocok dengan 'ganjil' dan legacy '1'
    - genap cocok dengan 'genap' dan legacy '2'
    """
    normalized = normalisasi_semester(value)
    return ["genap", "2"] if normalized == "genap" else ["ganjil", "1"]


def _is_semester_all(value):
    text = str(value or "").strip().lower()
    return text in ["", "all", "ganjilgenap", "ganjil genap", "1 tahun ajaran", "setahun"]


def _jadwal_satu_mapel_kelas(jadwal):
    if _status_value(jadwal) != "aktif" or _status_value(getattr(jadwal, "kelas", None)) != "aktif":
        return []

    return [
        row.id_jadwal
        for row in Jadwal.query.filter_by(
            id_kelas=jadwal.id_kelas,
            id_mapel=jadwal.id_mapel,
            status="aktif",
        ).all()
    ]


def _filter_semester_tahun(query):
    semester = request.args.get("semester")
    tahun_ajaran = request.args.get("tahun_ajaran") or request.args.get("tahun")

    if semester and not _is_semester_all(semester):
        query = query.filter(Nilai.semester.in_(_semester_filter_values(semester)))

    if tahun_ajaran:
        query = query.filter(Nilai.tahun_ajaran == tahun_ajaran)

    return query


def jadwal_milik_guru(id_jadwal: int, id_guru: int) -> bool:
    return db.session.query(JadwalGuru).filter_by(
        id_jadwal=id_jadwal,
        id_guru=id_guru
    ).first() is not None



def _status_value(obj, default="aktif"):
    value = getattr(obj, "status", None)
    if value is None:
        return default
    value = str(value).strip().lower()
    return value or default


def _apply_status_filter(query, status="aktif"):
    """
    Filter nilai berdasarkan status kelas dan jadwal.
    - aktif   : hanya kelas dan jadwal aktif
    - riwayat : kelas/jadwal yang sudah selesai/arsip/nonaktif
    - all     : semua nilai, dipakai halaman murid agar nilai lama tetap terlihat
    """
    status = (status or "aktif").lower().strip()

    if status == "all":
        return query

    if status in ["riwayat", "arsip", "selesai", "nonaktif"]:
        return query.filter(
            or_(
                Kelas.status != "aktif",
                Jadwal.status != "aktif",
            )
        )

    return query.filter(Kelas.status == "aktif", Jadwal.status == "aktif")


def _murid_aktif_di_kelas(id_kelas):
    murid_list = (
        db.session.query(Murid)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .filter(
            MuridTingkat.id_kelas == id_kelas,
            MuridTingkat.status == "aktif",
        )
        .order_by(Murid.nama_murid.asc())
        .all()
    )
    if murid_list:
        return murid_list
    return Murid.query.filter_by(id_kelas=id_kelas).order_by(Murid.nama_murid.asc()).all()


def _murid_masih_aktif_di_kelas(id_murid, id_kelas):
    return MuridTingkat.query.filter_by(
        id_murid=id_murid,
        id_kelas=id_kelas,
        status="aktif",
    ).first() is not None


def tingkat_text(kelas):
    tingkat = getattr(kelas, "tingkat", None)
    if tingkat and getattr(tingkat, "pangkat", None) is not None:
        return str(tingkat.pangkat)

    id_tingkat = getattr(kelas, "id_tingkat", None)
    return str(id_tingkat) if id_tingkat is not None else "-"


def tingkat_payload(kelas):
    return {
        "id_tingkat": getattr(kelas, "id_tingkat", None),
        "tingkat": tingkat_text(kelas),
        "pangkat": tingkat_text(kelas),
    }


def jadwal_payload(jadwal, kelas, mapel):
    return {
        "id_jadwal": jadwal.id_jadwal,
        "id_kelas": jadwal.id_kelas,
        "id_mapel": jadwal.id_mapel,
        **tingkat_payload(kelas),
        "kelas": kelas.nama_kelas,
        "nama_kelas": kelas.nama_kelas,
        "tahun_ajaran": kelas.tahun_ajaran,
        "tahun": kelas.tahun_ajaran,
        "mapel": mapel.nama_mapel,
        "nama_mapel": mapel.nama_mapel,
        "hari": jadwal.hari,
        "jam_mulai": str(jadwal.jam_mulai)[:5] if jadwal.jam_mulai else "",
        "jam_selesai": str(jadwal.jam_selesai)[:5] if jadwal.jam_selesai else "",
        "status": getattr(jadwal, "status", "aktif"),
        "status_kelas": getattr(kelas, "status", "aktif"),
    }


def kelompok_nilai(kelas, jadwal):
    status_kelas = getattr(kelas, "status", "aktif") or "aktif"
    status_jadwal = getattr(jadwal, "status", "aktif") or "aktif"

    if status_kelas == "aktif" and status_jadwal == "aktif":
        return "aktif"

    return "riwayat"


def nilai_payload(nilai, murid, jadwal, kelas, mapel, guru=None):
    status_kelas = getattr(kelas, "status", "aktif") or "aktif"
    status_jadwal = getattr(jadwal, "status", "aktif") or "aktif"

    return {
        "id": nilai.id_nilai,
        "id_nilai": nilai.id_nilai,
        "id_jadwal": jadwal.id_jadwal,
        "id_murid": murid.id_murid,

        "murid": murid.nama_murid,
        "nama_murid": murid.nama_murid,
        "nis": murid.nis,

        "id_kelas": kelas.id_kelas,
        "kelas": kelas.nama_kelas,
        "nama_kelas": kelas.nama_kelas,

        **tingkat_payload(kelas),

        "id_mapel": mapel.id_mapel,
        "mapel": mapel.nama_mapel,
        "nama_mapel": mapel.nama_mapel,

        "guru": guru.nama_guru if guru else None,

        "semester": nilai.semester,
        "tahun": nilai.tahun_ajaran,
        "tahun_ajaran": nilai.tahun_ajaran,

        "nilai": nilai.nilai_angka,
        "nilai_angka": nilai.nilai_angka,
        "huruf": nilai.nilai_huruf,
        "nilai_huruf": nilai.nilai_huruf,

        "kirim": nilai.status_kirim,
        "status_kirim": nilai.status_kirim,

        "status_kelas": status_kelas,
        "status_jadwal": status_jadwal,
        "kelompok_nilai": kelompok_nilai(kelas, jadwal),
    }


# =====================================================
# ✅ INPUT NILAI (BERDASARKAN JADWAL)
# =====================================================
@nilai_bp.route("/guru/nilai", methods=["POST"])
@jwt_required()
def input_nilai():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    data = request.json or {}

    id_jadwal = data.get("id_jadwal")
    id_murid = data.get("id_murid")
    semester = normalisasi_semester(data.get("semester"))
    tahun_ajaran = data.get("tahun_ajaran")
    nilai_angka = data.get("nilai_angka")

    if id_jadwal is None or id_murid is None or not tahun_ajaran or nilai_angka is None:
        return jsonify({"message": "Data tidak lengkap"}), 400

    try:
        nilai = float(nilai_angka)
    except Exception:
        return jsonify({"message": "Nilai harus angka"}), 400

    if nilai < 0 or nilai > 100:
        return jsonify({"message": "Nilai 0 - 100"}), 400

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    if not jadwal_milik_guru(int(id_jadwal), int(id_guru)):
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)

    if _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify({"message": "Jadwal atau kelas sudah arsip, tidak dapat input nilai baru"}), 400

    murid = Murid.query.get_or_404(id_murid)
    if murid.id_kelas != jadwal.id_kelas and not _murid_masih_aktif_di_kelas(id_murid, jadwal.id_kelas):
        return jsonify({"message": "Murid bukan kelas aktif jadwal ini"}), 403

    jadwal_satu_kelompok = _jadwal_satu_mapel_kelas(jadwal)
    cek = Nilai.query.filter(
        Nilai.id_jadwal.in_(jadwal_satu_kelompok),
        Nilai.id_murid == id_murid,
        Nilai.semester.in_(_semester_filter_values(semester)),
        Nilai.tahun_ajaran == tahun_ajaran,
    ).first()

    if cek:
        return jsonify({"message": "Nilai sudah ada, gunakan edit"}), 409

    huruf = konversi_huruf(nilai)

    new = Nilai(
        id_jadwal=id_jadwal,
        id_murid=id_murid,
        semester=semester,
        tahun_ajaran=tahun_ajaran,
        nilai_angka=nilai,
        nilai_huruf=huruf,
        status_kirim=False
    )

    db.session.add(new)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nilai sudah ada, gunakan edit"}), 409

    return jsonify({
        "message": "Nilai tersimpan",
        "id_nilai": new.id_nilai,
        "huruf": huruf,
        "id_tingkat": jadwal.kelas.id_tingkat if jadwal.kelas else None,
        "tingkat": tingkat_text(jadwal.kelas) if jadwal.kelas else "-",
    }), 201


# =====================================================
# ✅ NILAI MURID (JWT) - join ke guru via jadwal_guru
# =====================================================
# =====================================================
# ✅ NILAI MURID / ORANG TUA (JWT)
# =====================================================
@nilai_bp.route("/murid/nilai", methods=["GET"])
@jwt_required()
def nilai_murid():
    claims = get_jwt()
    role = claims.get("role")

    if role not in ["murid", "orang_tua"]:
        return jsonify({"message": "Akses ditolak"}), 403

    id_murid = claims.get("id_murid")

    if not id_murid:
        return jsonify({"message": "id_murid tidak ada di token"}), 400

    # Default all: murid/orang tua tetap bisa melihat nilai aktif dan riwayat lama.
    # Frontend akan memisahkan menjadi Semester Ganjil, Semester Genap, dan Riwayat.
    status = (request.args.get("status") or "aktif").lower().strip()

    q = (
        db.session.query(Nilai, Murid, Jadwal, Kelas, MataPelajaran, Guru)
        .join(Murid, Murid.id_murid == Nilai.id_murid)
        .join(Jadwal, Jadwal.id_jadwal == Nilai.id_jadwal)
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .outerjoin(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .outerjoin(Guru, Guru.id_guru == JadwalGuru.id_guru)
        .filter(Nilai.id_murid == id_murid)
    )

    q = _apply_status_filter(q, status)

    data = (
        q.order_by(
            Nilai.tahun_ajaran.desc(),
            Nilai.semester.asc(),
            Kelas.id_tingkat.desc(),
            MataPelajaran.nama_mapel.asc(),
        )
        .all()
    )

    return jsonify([
        nilai_payload(n, murid, j, k, m, g)
        for n, murid, j, k, m, g in data
    ]), 200

# =====================================================
# ✅ NILAI ADMIN / GURU (filter tetap)
# =====================================================
@nilai_bp.route("/admin/nilai", methods=["GET"])
@jwt_required()
def nilai_admin():
    claims = get_jwt()
    if claims.get("role") not in ["admin", "guru"]:
        return jsonify({"message": "Akses ditolak"}), 403

    q = (
        db.session.query(Nilai, Murid, Jadwal, Kelas, MataPelajaran, Guru)
        .join(Murid, Murid.id_murid == Nilai.id_murid)
        .join(Jadwal, Jadwal.id_jadwal == Nilai.id_jadwal)
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .outerjoin(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .outerjoin(Guru, Guru.id_guru == JadwalGuru.id_guru)
    )

    # Default all agar admin/guru bisa rekap nilai semester aktif maupun riwayat kapan saja.
    status = request.args.get("status", "aktif")
    q = _apply_status_filter(q, status)
    q = _filter_semester_tahun(q)

    # Untuk role admin, default wajib hanya nilai yang sudah dikirim guru.
    # Guru tetap bisa mengambil semua/yang belum terkirim ketika dibutuhkan oleh halaman laporkan nilai.
    kirim_default = "terkirim" if claims.get("role") == "admin" else "all"
    kirim = (request.args.get("kirim") or kirim_default).lower().strip()
    if kirim in ["terkirim", "true", "1"]:
        q = q.filter(Nilai.status_kirim == True)
    elif kirim in ["belum", "false", "0"]:
        q = q.filter(Nilai.status_kirim == False)

    if request.args.get("id_tingkat"):
        q = q.filter(Kelas.id_tingkat == request.args["id_tingkat"])

    if request.args.get("id_kelas"):
        q = q.filter(Jadwal.id_kelas == request.args["id_kelas"])

    if request.args.get("id_mapel"):
        q = q.filter(Jadwal.id_mapel == request.args["id_mapel"])

    if request.args.get("id_murid"):
        q = q.filter(Nilai.id_murid == request.args["id_murid"])

    data = q.order_by(Nilai.tahun_ajaran.desc(), Nilai.semester.desc()).all()

    return jsonify([
        nilai_payload(n, mur, j, k, m, g)
        for n, mur, j, k, m, g in data
    ]), 200


# =====================================================
# ✅ EDIT NILAI - validasi via jadwal_guru
# =====================================================
@nilai_bp.route("/guru/nilai/<int:id_nilai>", methods=["PUT"])
@jwt_required()
def edit_nilai(id_nilai):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    nilai = Nilai.query.get_or_404(id_nilai)

    if not jadwal_milik_guru(nilai.id_jadwal, id_guru):
        return jsonify({"message": "Bukan nilai anda"}), 403

    jadwal = Jadwal.query.get(nilai.id_jadwal)
    if not jadwal or _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify({"message": "Nilai pada jadwal/kelas selesai tidak dapat diubah"}), 400

    data = request.json or {}

    if "nilai_angka" in data:
        try:
            angka = float(data["nilai_angka"])
        except Exception:
            return jsonify({"message": "Nilai invalid"}), 400

        if angka < 0 or angka > 100:
            return jsonify({"message": "Nilai 0-100"}), 400

        nilai.nilai_angka = angka
        nilai.nilai_huruf = konversi_huruf(angka)

    if "semester" in data:
        nilai.semester = normalisasi_semester(data["semester"])

    if "tahun_ajaran" in data:
        nilai.tahun_ajaran = data["tahun_ajaran"]

    # Jika nilai yang sudah terkirim diedit lagi, admin tidak boleh melihat
    # perubahan baru sebelum guru menekan kirim ulang.
    nilai.status_kirim = False

    db.session.commit()
    return jsonify({"message": "Nilai diperbarui. Silakan kirim ulang ke admin."}), 200


# =====================================================
# ✅ DELETE NILAI - validasi via jadwal_guru
# =====================================================
@nilai_bp.route("/guru/nilai/<int:id_nilai>", methods=["DELETE"])
@jwt_required()
def delete_nilai(id_nilai):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    nilai = Nilai.query.get_or_404(id_nilai)

    if not jadwal_milik_guru(nilai.id_jadwal, id_guru):
        return jsonify({"message": "Bukan nilai anda"}), 403

    jadwal = Jadwal.query.get(nilai.id_jadwal)
    if not jadwal or _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify({"message": "Nilai pada jadwal/kelas selesai tidak dapat dihapus"}), 400

    db.session.delete(nilai)
    db.session.commit()
    return jsonify({"message": "Nilai dihapus"}), 200


# =====================================================
# ✅ KIRIM KE ADMIN (guru)
# =====================================================
@nilai_bp.route("/admin/nilai/kirim/<int:id_nilai>", methods=["POST"])
@jwt_required()
def kirim_admin(id_nilai):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    nilai = Nilai.query.get_or_404(id_nilai)

    if not jadwal_milik_guru(nilai.id_jadwal, id_guru):
        return jsonify({"message": "Bukan nilai anda"}), 403

    nilai.status_kirim = True
    db.session.commit()
    return jsonify({"message": "Nilai dikirim ke admin"}), 200


# =====================================================
# ✅ GURU: REKAP NILAI BELUM DIKIRIM
# =====================================================
@nilai_bp.route("/guru/nilai/rekap", methods=["GET"])
@jwt_required()
def rekap_nilai_guru():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")

    id_tingkat = request.args.get("id_tingkat", type=int)
    id_kelas = request.args.get("id_kelas", type=int)
    id_mapel = request.args.get("id_mapel", type=int)

    q = (
        db.session.query(Nilai, Murid, Jadwal, Kelas, MataPelajaran)
        .join(Murid, Murid.id_murid == Nilai.id_murid)
        .join(Jadwal, Jadwal.id_jadwal == Nilai.id_jadwal)
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .join(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .filter(JadwalGuru.id_guru == id_guru)
    )

    status = request.args.get("status", "aktif")
    q = _apply_status_filter(q, status)
    q = _filter_semester_tahun(q)

    kirim = (request.args.get("kirim") or "belum").lower().strip()
    if kirim in ["belum", "false", "0"]:
        q = q.filter(Nilai.status_kirim == False)
    elif kirim in ["terkirim", "true", "1"]:
        q = q.filter(Nilai.status_kirim == True)

    if id_tingkat:
        q = q.filter(Kelas.id_tingkat == id_tingkat)

    if id_kelas:
        q = q.filter(Jadwal.id_kelas == id_kelas)

    if id_mapel:
        q = q.filter(Jadwal.id_mapel == id_mapel)

    data = q.all()

    return jsonify([
        {
            "id_nilai": n.id_nilai,
            "id_jadwal": j.id_jadwal,
            "id_murid": mur.id_murid,
            "nama_murid": mur.nama_murid,
            "murid": mur.nama_murid,
            "nis": mur.nis,
            "id_kelas": k.id_kelas,
            "nama_kelas": k.nama_kelas,
            "kelas": k.nama_kelas,
            **tingkat_payload(k),
            "id_mapel": m.id_mapel,
            "nama_mapel": m.nama_mapel,
            "mapel": m.nama_mapel,
            "semester": n.semester,
            "tahun": n.tahun_ajaran,
            "tahun_ajaran": n.tahun_ajaran,
            "nilai_angka": n.nilai_angka,
            "nilai": n.nilai_angka,
            "nilai_huruf": n.nilai_huruf,
            "huruf": n.nilai_huruf,
            "kirim": n.status_kirim,
            "status_kirim": n.status_kirim,
            "status_jadwal": _status_value(j),
            "status_kelas": _status_value(k),
        }
        for n, mur, j, k, m in data
    ]), 200


# =====================================================
# ✅ GURU: LIST JADWAL UNTUK NILAI + TINGKAT
# frontend: GET /api/guru/jadwal-nilai
# =====================================================
@nilai_bp.route("/guru/jadwal-nilai", methods=["GET"])
@jwt_required()
def jadwal_guru_nilai():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    data = (
        db.session.query(Jadwal, Kelas, MataPelajaran)
        .join(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .filter(
            JadwalGuru.id_guru == id_guru,
            Kelas.status == "aktif",
            Jadwal.status == "aktif"
        )
        .order_by(Kelas.id_tingkat.asc(), Kelas.nama_kelas.asc(), MataPelajaran.nama_mapel.asc())
        .all()
    )

    return jsonify([
        jadwal_payload(j, k, m)
        for j, k, m in data
    ]), 200


@nilai_bp.route("/guru/nilai/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def get_murid_by_jadwal(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify([]), 200

    murid_list = _murid_aktif_di_kelas(jadwal.id_kelas)

    return jsonify([
        {
            "id_murid": m.id_murid,
            "nama_murid": m.nama_murid,
            "nis": getattr(m, "nis", None),
            "id_kelas": jadwal.id_kelas,
            "id_tingkat": jadwal.kelas.id_tingkat if jadwal.kelas else None,
            "tingkat": tingkat_text(jadwal.kelas) if jadwal.kelas else "-",
            "pangkat": tingkat_text(jadwal.kelas) if jadwal.kelas else "-",
        }
        for m in murid_list
    ]), 200


# =====================================================
# ✅ GURU: LIST NILAI BERDASARKAN JADWAL
# frontend: GET /api/guru/nilai/jadwal/<id_jadwal>
# =====================================================
@nilai_bp.route("/guru/nilai/jadwal/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def get_nilai_by_jadwal_guru(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify([]), 200

    jadwal_satu_kelompok = _jadwal_satu_mapel_kelas(jadwal)

    data = (
        db.session.query(Nilai, Murid, Jadwal, Kelas, MataPelajaran, Guru)
        .join(Murid, Murid.id_murid == Nilai.id_murid)
        .join(Jadwal, Jadwal.id_jadwal == Nilai.id_jadwal)
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .outerjoin(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .outerjoin(Guru, Guru.id_guru == JadwalGuru.id_guru)
        .filter(Nilai.id_jadwal.in_(jadwal_satu_kelompok))
    )
    data = _filter_semester_tahun(data)
    data = (
        data
        .order_by(Murid.nama_murid.asc(), Nilai.semester.asc())
        .all()
    )

    return jsonify([
        nilai_payload(n, mur, j, k, m, g)
        for n, mur, j, k, m, g in data
    ]), 200


# =====================================================
# ✅ GURU: KIRIM SEMUA NILAI DALAM 1 JADWAL KE ADMIN
# frontend: POST /api/guru/nilai/kirim/<id_jadwal>
# =====================================================
@nilai_bp.route("/guru/nilai/kirim/<int:id_jadwal>", methods=["POST"])
@jwt_required()
def kirim_semua_nilai_jadwal_ke_admin(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify({"message": "Jadwal atau kelas sudah arsip, tidak dapat mengirim nilai"}), 400

    req = request.get_json(silent=True) or {}
    semester = request.args.get("semester") or req.get("semester")
    tahun_ajaran = request.args.get("tahun_ajaran") or request.args.get("tahun") or req.get("tahun_ajaran") or req.get("tahun")

    jadwal_satu_kelompok = _jadwal_satu_mapel_kelas(jadwal)
    nilai_query = Nilai.query.filter(Nilai.id_jadwal.in_(jadwal_satu_kelompok))

    if semester and not _is_semester_all(semester):
        nilai_query = nilai_query.filter(Nilai.semester.in_(_semester_filter_values(semester)))

    if tahun_ajaran:
        nilai_query = nilai_query.filter(Nilai.tahun_ajaran == tahun_ajaran)

    nilai_list = nilai_query.all()

    if not nilai_list:
        return jsonify({"message": "Belum ada nilai pada jadwal dan semester-tahun ajaran ini"}), 404

    for n in nilai_list:
        n.status_kirim = True

    db.session.commit()

    return jsonify({
        "message": "Semua nilai pada jadwal berhasil dikirim ke admin",
        "id_jadwal": id_jadwal,
        "jumlah": len(nilai_list),
        "id_tingkat": jadwal.kelas.id_tingkat if jadwal.kelas else None,
        "tingkat": tingkat_text(jadwal.kelas) if jadwal.kelas else "-",
    }), 200


# =====================================================
# ✅ ADMIN: LIHAT NILAI TERKIRIM BERDASARKAN JADWAL
# frontend: GET /api/admin/nilai/jadwal/<id_jadwal>
# =====================================================
@nilai_bp.route("/admin/nilai/jadwal/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def admin_nilai_by_jadwal(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Akses ditolak"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if _status_value(jadwal) != "aktif" or _status_value(jadwal.kelas) != "aktif":
        return jsonify([]), 200

    jadwal_satu_kelompok = _jadwal_satu_mapel_kelas(jadwal)

    data = (
        db.session.query(Nilai, Murid, Jadwal, Kelas, MataPelajaran, Guru)
        .join(Murid, Murid.id_murid == Nilai.id_murid)
        .join(Jadwal, Jadwal.id_jadwal == Nilai.id_jadwal)
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .outerjoin(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .outerjoin(Guru, Guru.id_guru == JadwalGuru.id_guru)
        .filter(Nilai.id_jadwal.in_(jadwal_satu_kelompok))
    )

    kirim = (request.args.get("kirim") or "terkirim").lower().strip()
    if kirim in ["terkirim", "true", "1"]:
        data = data.filter(Nilai.status_kirim == True)
    elif kirim in ["belum", "false", "0"]:
        data = data.filter(Nilai.status_kirim == False)

    status = request.args.get("status", "aktif")
    data = _apply_status_filter(data, status)
    data = _filter_semester_tahun(data)

    data = data.order_by(Murid.nama_murid.asc(), Nilai.semester.asc()).all()

    return jsonify([
        nilai_payload(n, mur, j, k, m, g)
        for n, mur, j, k, m, g in data
    ]), 200


# =====================================================
# ✅ ADMIN: LIST SEMUA JADWAL
# frontend: GET /api/jadwal
# =====================================================
