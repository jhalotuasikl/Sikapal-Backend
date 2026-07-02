# app/routes/guru.py
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt

from app.extensions import db
from app.models.kelas import Kelas
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.tingkat import Tingkat

# Helper absensi tetap memakai fungsi inti dari modul kehadiran agar tidak ada duplikasi logic rekap.
from .kehadiran import (
    jadwal_milik_guru,
    _jadwal_group_ids_by_id,
    _jadwal_kelas_aktif,
    _rekap_absensi_mapel,
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

    semester = request.args.get("semester")
    tahun_ajaran = request.args.get("tahun_ajaran") or request.args.get("tahun")

    return jsonify(
        _rekap_absensi_mapel(
            jadwal,
            id_jadwal_group,
            semester=semester,
            tahun_ajaran=tahun_ajaran,
        )
    ), 200
