# app/routes/periode_akademik.py
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt

from app import db
from app.models.periode_akademik import PeriodeAkademik

periode_akademik_bp = Blueprint("periode_akademik", __name__)


def _is_admin():
    return (get_jwt() or {}).get("role") == "admin"


def _clean(value):
    return str(value or "").strip()


def _semester(value):
    text = _clean(value).lower()
    if text in {"2", "genap", "semester 2", "semester genap"}:
        return "genap"
    if text in {"1", "ganjil", "semester 1", "semester ganjil"}:
        return "ganjil"
    return ""


def _parse_date(value, field_name):
    text = _clean(value)
    try:
        y, m, d = map(int, text.split("-"))
        return date(y, m, d), None
    except Exception:
        return None, f"{field_name} harus format YYYY-MM-DD"


def _payload(row):
    return row.to_dict() if row else None


@periode_akademik_bp.route("/periode/aktif", methods=["GET"])
@jwt_required()
def periode_aktif():
    row = PeriodeAkademik.aktif()
    if not row:
        return jsonify({
            "success": False,
            "message": "Belum ada periode akademik aktif",
            "data": None,
        }), 404

    return jsonify({
        "success": True,
        "data": _payload(row),
    }), 200


@periode_akademik_bp.route("/admin/periode", methods=["GET"])
@jwt_required()
def list_periode():
    if not _is_admin():
        return jsonify({"message": "Akses khusus admin"}), 403

    rows = (
        PeriodeAkademik.query
        .order_by(PeriodeAkademik.status.asc(), PeriodeAkademik.tanggal_mulai.desc(), PeriodeAkademik.id_periode.desc())
        .all()
    )

    return jsonify({
        "success": True,
        "data": [_payload(r) for r in rows],
    }), 200


@periode_akademik_bp.route("/admin/periode", methods=["POST"])
@jwt_required()
def tambah_periode():
    if not _is_admin():
        return jsonify({"message": "Akses khusus admin"}), 403

    data = request.get_json(silent=True) or {}
    tahun_ajaran = _clean(data.get("tahun_ajaran"))
    semester = _semester(data.get("semester"))
    status = _clean(data.get("status") or "selesai").lower()
    tanggal_mulai, err_mulai = _parse_date(data.get("tanggal_mulai"), "tanggal_mulai")
    tanggal_selesai, err_selesai = _parse_date(data.get("tanggal_selesai"), "tanggal_selesai")

    if not tahun_ajaran or not semester or not tanggal_mulai or not tanggal_selesai:
        return jsonify({
            "message": err_mulai or err_selesai or "tahun_ajaran, semester, tanggal_mulai, dan tanggal_selesai wajib diisi",
        }), 400

    if tanggal_selesai < tanggal_mulai:
        return jsonify({"message": "tanggal_selesai tidak boleh lebih awal dari tanggal_mulai"}), 400

    if status not in {"aktif", "selesai"}:
        status = "selesai"

    try:
        if status == "aktif":
            PeriodeAkademik.query.filter(PeriodeAkademik.status == "aktif").update({"status": "selesai"})

        row = PeriodeAkademik(
            tahun_ajaran=tahun_ajaran,
            semester=semester,
            tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai,
            status=status,
        )
        db.session.add(row)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Periode akademik berhasil ditambahkan",
            "data": _payload(row),
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Gagal menambah periode: {str(e)}"}), 500


@periode_akademik_bp.route("/admin/periode/<int:id_periode>", methods=["PUT"])
@jwt_required()
def ubah_periode(id_periode):
    if not _is_admin():
        return jsonify({"message": "Akses khusus admin"}), 403

    row = PeriodeAkademik.query.get_or_404(id_periode)
    data = request.get_json(silent=True) or {}

    tahun_ajaran = _clean(data.get("tahun_ajaran") or row.tahun_ajaran)
    semester = _semester(data.get("semester") or row.semester)
    status = _clean(data.get("status") or row.status).lower()

    tanggal_mulai = row.tanggal_mulai
    tanggal_selesai = row.tanggal_selesai

    if "tanggal_mulai" in data:
        tanggal_mulai, err = _parse_date(data.get("tanggal_mulai"), "tanggal_mulai")
        if err:
            return jsonify({"message": err}), 400

    if "tanggal_selesai" in data:
        tanggal_selesai, err = _parse_date(data.get("tanggal_selesai"), "tanggal_selesai")
        if err:
            return jsonify({"message": err}), 400

    if not tahun_ajaran or not semester:
        return jsonify({"message": "tahun_ajaran dan semester wajib diisi"}), 400

    if tanggal_selesai < tanggal_mulai:
        return jsonify({"message": "tanggal_selesai tidak boleh lebih awal dari tanggal_mulai"}), 400

    if status not in {"aktif", "selesai"}:
        status = row.status or "selesai"

    try:
        if status == "aktif":
            PeriodeAkademik.query.filter(PeriodeAkademik.id_periode != id_periode).update({"status": "selesai"})

        row.tahun_ajaran = tahun_ajaran
        row.semester = semester
        row.tanggal_mulai = tanggal_mulai
        row.tanggal_selesai = tanggal_selesai
        row.status = status
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Periode akademik berhasil diperbarui",
            "data": _payload(row),
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Gagal mengubah periode: {str(e)}"}), 500


@periode_akademik_bp.route("/admin/periode/<int:id_periode>/aktifkan", methods=["PUT"])
@jwt_required()
def aktifkan_periode(id_periode):
    if not _is_admin():
        return jsonify({"message": "Akses khusus admin"}), 403

    row = PeriodeAkademik.query.get_or_404(id_periode)

    try:
        PeriodeAkademik.query.filter(PeriodeAkademik.id_periode != id_periode).update({"status": "selesai"})
        row.status = "aktif"
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Periode akademik aktif berhasil diganti",
            "data": _payload(row),
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Gagal mengaktifkan periode: {str(e)}"}), 500
