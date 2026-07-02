from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, verify_jwt_in_request, get_jwt
from app import db
from app.models.tingkat import Tingkat

admin_tingkat_bp = Blueprint("admin_tingkat", __name__)


@admin_tingkat_bp.before_request
def _guard_admin_tingkat():
    if request.method == "OPTIONS":
        return None

    verify_jwt_in_request()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Akses khusus admin"}), 403

    return None


# =====================
# LIST
# =====================
@admin_tingkat_bp.route("/tingkat", methods=["GET"])
@jwt_required()
def list_tingkat():

    data = Tingkat.query.all()

    return jsonify([
        {
            "id_tingkat": t.id_tingkat,
            "pangkat": t.pangkat
        }
        for t in data
    ]), 200


# =====================
# CREATE
# =====================
@admin_tingkat_bp.route("/tingkat", methods=["POST"])
@jwt_required()
def tambah_tingkat():

    data = request.json

    if not data or not data.get("pangkat"):
        return jsonify({"message": "Pangkat wajib"}), 400

    # CEK DUPLIKAT
    if Tingkat.query.filter_by(pangkat=data["pangkat"]).first():
        return jsonify({"message": "Tingkat sudah ada"}), 400

    tingkat = Tingkat(
        pangkat=data["pangkat"]
    )

    db.session.add(tingkat)
    db.session.commit()

    return jsonify({"message": "Tingkat ditambahkan"}), 201


# =====================
# UPDATE
# =====================
@admin_tingkat_bp.route("/tingkat/<int:id_tingkat>", methods=["PUT"])
@jwt_required()
def update_tingkat(id_tingkat):

    data = request.json

    if not data or not data.get("pangkat"):
        return jsonify({"message": "Data kosong"}), 400

    tingkat = Tingkat.query.get_or_404(id_tingkat)

    # CEK DUPLIKAT
    if Tingkat.query.filter(
        Tingkat.pangkat == data["pangkat"],
        Tingkat.id_tingkat != id_tingkat
    ).first():

        return jsonify({"message": "Pangkat sudah digunakan"}), 400


    tingkat.pangkat = data["pangkat"]

    db.session.commit()

    return jsonify({"message": "Tingkat diperbarui"}), 200


# =====================
# DELETE
# =====================
@admin_tingkat_bp.route("/tingkat/<int:id_tingkat>", methods=["DELETE"])
@jwt_required()
def hapus_tingkat(id_tingkat):

    tingkat = Tingkat.query.get_or_404(id_tingkat)

    try:

        db.session.delete(tingkat)
        db.session.commit()

    except Exception as e:

        db.session.rollback()

        return jsonify({
            "message": "Gagal hapus tingkat",
            "error": str(e)
        }), 500


    return jsonify({"message": "Tingkat dihapus"}), 200
