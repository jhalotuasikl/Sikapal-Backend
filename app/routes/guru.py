# app/routes/guru.py
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt

from app.extensions import db
from app.models.kelas import Kelas
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.kehadiran_murid import KehadiranMurid
from app.models.tingkat import Tingkat

# Helper absensi tetap memakai fungsi inti dari modul kehadiran agar tidak ada duplikasi logic rekap.
from .kehadiran import (
    jadwal_milik_guru,
    _jadwal_group_ids_by_id,
    _jadwal_kelas_aktif,
    _rekap_absensi_mapel,
    _periode_aktif_values,
    _normalisasi_semester_kehadiran,
    _pertemuan_range_from_mode,
)

guru_bp = Blueprint("guru", __name__)


def _guard_guru():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return None, (jsonify({"message": "Khusus guru"}), 403)

    id_guru = claims.get("id_guru")
    if not id_guru:
        return None, (jsonify({"message": "id_guru tidak ada di token"}), 400)

    return int(id_guru), None


@guru_bp.route("/guru/tingkat", methods=["GET"])
@jwt_required()
def get_tingkat_guru_login():
    """Ambil daftar tingkat yang relevan untuk guru login.

    Endpoint ini dipakai halaman guru agar tidak lagi mengambil /admin/tingkat
    yang memang khusus admin dan akan menghasilkan 403 untuk role guru.
    Payload dibuat sama seperti admin_tingkat: id_tingkat dan pangkat.
    """
    id_guru, error = _guard_guru()
    if error:
        return error

    data = (
        db.session.query(Tingkat)
        .join(Kelas, Kelas.id_tingkat == Tingkat.id_tingkat)
        .join(Jadwal, Jadwal.id_kelas == Kelas.id_kelas)
        .join(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .filter(
            JadwalGuru.id_guru == id_guru,
            Jadwal.status == "aktif",
            Kelas.status == "aktif",
        )
        .distinct()
        .order_by(Tingkat.pangkat.asc())
        .all()
    )

    return jsonify([
        {
            "id_tingkat": t.id_tingkat,
            "pangkat": t.pangkat,
        }
        for t in data
    ]), 200


@guru_bp.route("/guru/kelas", methods=["GET"])
@jwt_required()
def get_kelas_guru_login():
    id_guru, error = _guard_guru()
    if error:
        return error

    kelas_list = (
        db.session.query(Kelas)
        .join(Jadwal, Jadwal.id_kelas == Kelas.id_kelas)
        .join(JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal)
        .filter(
            JadwalGuru.id_guru == id_guru,
            Jadwal.status == "aktif",
            Kelas.status == "aktif",
        )
        .distinct()
        .order_by(Kelas.id_tingkat.asc(), Kelas.nama_kelas.asc())
        .all()
    )

    return jsonify([
        {
            "id_kelas": k.id_kelas,
            "nama_kelas": k.nama_kelas,
            "tahun_ajaran": k.tahun_ajaran,
            "id_tingkat": k.id_tingkat,
            "status": getattr(k, "status", None),
            "status_kelas": getattr(k, "status", None),
        }
        for k in kelas_list
    ]), 200


# =====================================================
# GURU KIRIM REKAP ABSENSI KE ADMIN
# =====================================================
@guru_bp.route("/guru/absensi", methods=["POST"])
@jwt_required()
def guru_kirim_absensi_ke_admin():
    """Tandai rekap absensi guru sebagai terkirim agar bisa dibaca admin.

    Data absensi tetap disimpan saat guru input kehadiran. Endpoint ini hanya
    mengubah status_kirim=True pada data periode akademik aktif, sehingga
    admin tetap tidak bisa melihat absensi yang belum dikirim guru.
    """
    id_guru, error = _guard_guru()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    id_jadwal = data.get("id_jadwal")
    id_jadwal_list = data.get("id_jadwal_list") or []
    rekap = data.get("rekap", [])

    if not id_jadwal:
        return jsonify({"message": "id_jadwal wajib"}), 400

    try:
        id_jadwal = int(id_jadwal)
    except Exception:
        return jsonify({"message": "id_jadwal tidak valid"}), 400

    if not isinstance(rekap, list):
        return jsonify({"message": "rekap harus berupa list"}), 400

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal bukan milik guru login"}), 403

    jadwal, jadwal_group = _jadwal_group_ids_by_id(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404

    if not _jadwal_kelas_aktif(jadwal):
        return jsonify({"message": "Jadwal/kelas sudah selesai"}), 403

    periode_aktif, semester, tahun_ajaran = _periode_aktif_values()
    if not periode_aktif:
        return jsonify({"message": "Periode akademik aktif belum diatur"}), 400

    semester_norm = _normalisasi_semester_kehadiran(semester)
    awal, akhir = _pertemuan_range_from_mode(semester)

    rows_query = KehadiranMurid.query.filter(
        KehadiranMurid.id_jadwal.in_(jadwal_group),
        KehadiranMurid.pertemuan >= awal,
        KehadiranMurid.pertemuan <= akhir,
    )

    if semester_norm:
        rows_query = rows_query.filter(KehadiranMurid.semester == semester_norm)

    if tahun_ajaran:
        rows_query = rows_query.filter(KehadiranMurid.tahun_ajaran == tahun_ajaran)

    rows_terkirim = rows_query.all()
    if not rows_terkirim:
        return jsonify({
            "message": "Belum ada data absensi pada jadwal dan semester-tahun ajaran ini"
        }), 404

    for row in rows_terkirim:
        row.status_kirim = True

    db.session.commit()

    return jsonify({
        "message": "Rekap absensi berhasil dikirim ke admin",
        "id_jadwal": id_jadwal,
        "id_jadwal_group": id_jadwal_list or jadwal_group,
        "semester": semester_norm,
        "tahun_ajaran": tahun_ajaran,
        "jumlah": len(rekap),
        "jumlah_data_terkirim": len(rows_terkirim),
    }), 201


@guru_bp.route("/guru/rekap-absensi/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def guru_rekap_absensi_by_jadwal(id_jadwal):
    id_guru, error = _guard_guru()
    if error:
        return error

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak ditemukan / bukan milik guru"}), 404

    jadwal, id_jadwal_group = _jadwal_group_ids_by_id(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify([]), 200

    _periode, semester_aktif, tahun_aktif = _periode_aktif_values()
    semester = request.args.get("semester") or semester_aktif
    tahun_ajaran = request.args.get("tahun_ajaran") or request.args.get("tahun") or tahun_aktif

    return jsonify(
        _rekap_absensi_mapel(
            jadwal,
            id_jadwal_group,
            semester=semester,
            tahun_ajaran=tahun_ajaran,
        )
    ), 200
