from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime
from sqlalchemy import text

from app.extensions import db
from app.models.pengaduan import Pengaduan
from app.models.murid import Murid

pengaduan_bp = Blueprint("pengaduan", __name__)


def _to_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_murid_from_user(identity):
    murid = Murid.query.filter_by(id_user=identity).first()
    return murid.id_murid if murid else None


def _get_orang_tua_from_db(identity=None, id_ortu=None):
    try:
        if id_ortu:
            row = db.session.execute(
                text("SELECT id_ortu, id_murid FROM orang_tua WHERE id_ortu = :id_ortu LIMIT 1"),
                {"id_ortu": id_ortu},
            ).mappings().first()
            if row:
                return _to_int(row.get("id_ortu")), _to_int(row.get("id_murid"))

        if identity:
            row = db.session.execute(
                text("SELECT id_ortu, id_murid FROM orang_tua WHERE id_user = :id_user LIMIT 1"),
                {"id_user": identity},
            ).mappings().first()
            if row:
                return _to_int(row.get("id_ortu")), _to_int(row.get("id_murid"))
    except Exception:
        pass

    return None, None


def get_pelapor_from_token(claims, identity):
    role = (claims.get("role") or "").lower()

    if role == "murid":
        id_murid = _to_int(claims.get("id_murid")) or _get_murid_from_user(identity)
        if not id_murid:
            return None, None, None, jsonify({"message": "Data murid tidak ditemukan"}), 404
        return id_murid, None, "murid", None, None

    if role in ["orang_tua", "ortu", "orangtua"]:
        id_ortu = _to_int(claims.get("id_ortu"))
        id_murid = _to_int(claims.get("id_murid"))

        if not id_ortu or not id_murid:
            db_id_ortu, db_id_murid = _get_orang_tua_from_db(identity=identity, id_ortu=id_ortu)
            id_ortu = id_ortu or db_id_ortu
            id_murid = id_murid or db_id_murid

        if not id_ortu:
            return None, None, None, jsonify({"message": "Data orang tua tidak ditemukan"}), 404

        if not id_murid:
            return None, None, None, jsonify({"message": "Data anak/murid orang tua tidak ditemukan"}), 404

        return id_murid, id_ortu, "orang_tua", None, None

    return None, None, None, jsonify({"message": "Hanya murid atau orang tua yang dapat mengakses pengaduan"}), 403


def _samarkan_jika_anonim(item, row):
    if item.mode_pelaporan == "anonim":
        row["pelapor_display"] = "Anonim"
        row["nama_murid"] = "Anonim"
        row["nama_ortu"] = None
        row["nis"] = None
        row["id_murid"] = None
        row["id_ortu"] = None
        row["id_kelas"] = None
        row["nama_kelas"] = None
    return row


# =========================================================
# MURID / ORANG TUA: KIRIM PENGADUAN
# POST /api/pengaduan
# =========================================================
@pengaduan_bp.route("/pengaduan", methods=["POST"])
@jwt_required()
def create_pengaduan():
    claims = get_jwt()
    identity = get_jwt_identity()

    id_murid, id_ortu, tipe_pelapor, error, status_code = get_pelapor_from_token(claims, identity)
    if error:
        return error, status_code

    data = request.get_json() or {}

    jenis_laporan = data.get("jenis_laporan", "pengaduan")
    mode_pelaporan = data.get("mode_pelaporan")
    kategori_pengaduan = data.get("kategori_pengaduan")
    isi_pengaduan = data.get("isi_pengaduan")

    if not mode_pelaporan:
        return jsonify({"message": "mode_pelaporan wajib diisi"}), 400

    if not kategori_pengaduan:
        return jsonify({"message": "kategori_pengaduan wajib diisi"}), 400

    if not isi_pengaduan or not str(isi_pengaduan).strip():
        return jsonify({"message": "isi_pengaduan wajib diisi"}), 400

    jenis_valid = ["pengaduan", "aspirasi"]
    mode_valid = ["terbuka", "rahasia", "anonim"]
    kategori_valid = [
        "akademik",
        "absensi",
        "nilai",
        "bullying",
        "fasilitas",
        "lainnya"
    ]

    if jenis_laporan not in jenis_valid:
        return jsonify({"message": "jenis_laporan tidak valid"}), 400

    if mode_pelaporan not in mode_valid:
        return jsonify({"message": "mode_pelaporan tidak valid"}), 400

    if kategori_pengaduan not in kategori_valid:
        return jsonify({"message": "kategori_pengaduan tidak valid"}), 400

    pengaduan = Pengaduan(
        id_murid=id_murid,
        id_ortu=id_ortu,
        tipe_pelapor=tipe_pelapor,
        jenis_laporan=jenis_laporan,
        mode_pelaporan=mode_pelaporan,
        kategori_pengaduan=kategori_pengaduan,
        isi_pengaduan=isi_pengaduan.strip(),
        status="menunggu"
    )

    db.session.add(pengaduan)
    db.session.commit()

    pesan = "Aspirasi berhasil dikirim" if jenis_laporan == "aspirasi" else "Pengaduan berhasil dikirim"

    return jsonify({
        "message": pesan,
        "data": pengaduan.to_dict()
    }), 201


# =========================================================
# MURID / ORANG TUA: LIHAT PENGADUAN SENDIRI
# GET /api/pengaduan/saya
# =========================================================
@pengaduan_bp.route("/pengaduan/saya", methods=["GET"])
@jwt_required()
def get_pengaduan_saya():
    claims = get_jwt()
    identity = get_jwt_identity()

    id_murid, id_ortu, tipe_pelapor, error, status_code = get_pelapor_from_token(claims, identity)
    if error:
        return error, status_code

    jenis_laporan = request.args.get("jenis_laporan")

    q = Pengaduan.query.filter(Pengaduan.tipe_pelapor == tipe_pelapor)

    if jenis_laporan in ["pengaduan", "aspirasi"]:
        q = q.filter(Pengaduan.jenis_laporan == jenis_laporan)

    if tipe_pelapor == "orang_tua":
        q = q.filter(Pengaduan.id_ortu == id_ortu)
    else:
        q = q.filter(Pengaduan.id_murid == id_murid)

    data = q.order_by(Pengaduan.id_pengaduan.desc()).all()

    return jsonify([item.to_dict() for item in data]), 200


# =========================================================
# ADMIN: LIHAT SEMUA PENGADUAN
# GET /api/admin/pengaduan
# optional: ?status=menunggu&kategori=absensi
# =========================================================
@pengaduan_bp.route("/admin/pengaduan", methods=["GET"])
@jwt_required()
def get_semua_pengaduan():
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    status = request.args.get("status")
    kategori = request.args.get("kategori")
    jenis_laporan = request.args.get("jenis_laporan")

    q = Pengaduan.query

    if status:
        q = q.filter(Pengaduan.status == status)

    if kategori:
        q = q.filter(Pengaduan.kategori_pengaduan == kategori)

    if jenis_laporan in ["pengaduan", "aspirasi"]:
        q = q.filter(Pengaduan.jenis_laporan == jenis_laporan)

    data = q.order_by(Pengaduan.id_pengaduan.desc()).all()
    hasil = [_samarkan_jika_anonim(item, item.to_dict()) for item in data]

    return jsonify(hasil), 200


# =========================================================
# ADMIN: DETAIL PENGADUAN
# GET /api/admin/pengaduan/<id_pengaduan>
# =========================================================
@pengaduan_bp.route("/admin/pengaduan/<int:id_pengaduan>", methods=["GET"])
@jwt_required()
def detail_pengaduan(id_pengaduan):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    item = Pengaduan.query.get(id_pengaduan)
    if not item:
        return jsonify({"message": "Pengaduan tidak ditemukan"}), 404

    return jsonify(_samarkan_jika_anonim(item, item.to_dict())), 200


# =========================================================
# ADMIN: UPDATE STATUS / CATATAN
# PUT /api/admin/pengaduan/<id_pengaduan>
# =========================================================
@pengaduan_bp.route("/admin/pengaduan/<int:id_pengaduan>", methods=["PUT"])
@jwt_required()
def update_pengaduan(id_pengaduan):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    item = Pengaduan.query.get(id_pengaduan)
    if not item:
        return jsonify({"message": "Pengaduan tidak ditemukan"}), 404

    data = request.get_json() or {}

    status_baru = data.get("status")
    catatan_admin = data.get("catatan_admin")

    status_valid = ["menunggu", "diproses", "selesai", "ditolak"]

    if status_baru and status_baru not in status_valid:
        return jsonify({"message": "status tidak valid"}), 400

    if status_baru:
        item.status = status_baru

    if catatan_admin is not None:
        item.catatan_admin = catatan_admin.strip() if str(catatan_admin).strip() else None

    item.tanggal_ditindaklanjuti = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "message": "Pengaduan berhasil diperbarui",
        "data": item.to_dict()
    }), 200


# =========================================================
# MURID / ORANG TUA: HAPUS PENGADUAN SENDIRI
# DELETE /api/pengaduan/<id_pengaduan>
# =========================================================
@pengaduan_bp.route("/pengaduan/<int:id_pengaduan>", methods=["DELETE"])
@jwt_required()
def delete_pengaduan_saya(id_pengaduan):
    claims = get_jwt()
    identity = get_jwt_identity()

    id_murid, id_ortu, tipe_pelapor, error, status_code = get_pelapor_from_token(claims, identity)
    if error:
        return error, status_code

    q = Pengaduan.query.filter(
        Pengaduan.id_pengaduan == id_pengaduan,
        Pengaduan.tipe_pelapor == tipe_pelapor,
    )

    if tipe_pelapor == "orang_tua":
        q = q.filter(Pengaduan.id_ortu == id_ortu)
    else:
        q = q.filter(Pengaduan.id_murid == id_murid)

    item = q.first()

    if not item:
        return jsonify({"message": "Pengaduan tidak ditemukan"}), 404

    if item.status != "menunggu":
        return jsonify({
            "message": "Laporan yang sudah diproses tidak dapat dihapus"
        }), 400

    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Laporan berhasil dihapus"}), 200


# =========================================================
# ADMIN: HAPUS PENGADUAN
# DELETE /api/admin/pengaduan/<id_pengaduan>
# =========================================================
@pengaduan_bp.route("/admin/pengaduan/<int:id_pengaduan>", methods=["DELETE"])
@jwt_required()
def delete_pengaduan_admin(id_pengaduan):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    item = Pengaduan.query.get(id_pengaduan)
    if not item:
        return jsonify({"message": "Pengaduan tidak ditemukan"}), 404

    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Laporan berhasil dihapus"}), 200
