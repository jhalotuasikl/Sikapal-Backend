from flask import Blueprint, request, jsonify

from flask_jwt_extended import jwt_required, get_jwt

from app import db

from app.models.mata_pelajaran import MataPelajaran
from app.models.kelas import Kelas
from app.models.jadwal import Jadwal


mapel_bp = Blueprint("mapel", __name__)


# =====================================================
# LIST MAPEL (ALL / BY TINGKAT)
# =====================================================
@mapel_bp.route("/mapel", methods=["GET"])
@jwt_required()
def list_mapel():

    id_tingkat = request.args.get("id_tingkat")


    query = MataPelajaran.query


    if id_tingkat:
        query = query.filter_by(id_tingkat=id_tingkat)


    mapels = query.order_by(
        MataPelajaran.nama_mapel.asc()
    ).all()


    return jsonify([
        {
            "id_mapel": m.id_mapel,
            "nama_mapel": m.nama_mapel,
            "id_tingkat": m.id_tingkat
        }
        for m in mapels
    ]), 200



# =====================================================
# DETAIL MAPEL
# =====================================================
@mapel_bp.route("/mapel/<int:id_mapel>", methods=["GET"])
@jwt_required()
def detail_mapel(id_mapel):

    m = MataPelajaran.query.get_or_404(id_mapel)


    return jsonify({
        "id_mapel": m.id_mapel,
        "nama_mapel": m.nama_mapel,
        "id_tingkat": m.id_tingkat
    }), 200



# =====================================================
# TAMBAH MAPEL (ADMIN)
# =====================================================
@mapel_bp.route("/mapel", methods=["POST"])
@jwt_required()
def tambah_mapel():

    claims = get_jwt()


    if claims["role"] != "admin":
        return jsonify({"message": "Hanya admin"}), 403


    data = request.json


    nama = data.get("nama_mapel")
    id_tingkat = data.get("id_tingkat")


    if not nama or not id_tingkat:
        return jsonify({"message": "Data wajib kosong"}), 400


    # ================= CEK DUPLIKAT =================

    exist = MataPelajaran.query.filter_by(
        nama_mapel=nama,
        id_tingkat=id_tingkat
    ).first()

    if exist:
        return jsonify({"message": "Mapel sudah ada"}), 409


    mapel = MataPelajaran(
        nama_mapel=nama.strip(),
        id_tingkat=id_tingkat
    )


    db.session.add(mapel)
    db.session.commit()


    return jsonify({
        "message": "Mapel dibuat",
        "id_mapel": mapel.id_mapel
    }), 201



# =====================================================
# UPDATE MAPEL (ADMIN)
# =====================================================
@mapel_bp.route("/mapel/<int:id_mapel>", methods=["PUT"])
@jwt_required()
def update_mapel(id_mapel):

    claims = get_jwt()


    if claims["role"] != "admin":
        return jsonify({"message": "Hanya admin"}), 403


    mapel = MataPelajaran.query.get_or_404(id_mapel)


    data = request.json


    nama = data.get("nama_mapel")
    id_tingkat = data.get("id_tingkat")


    if nama:
        mapel.nama_mapel = nama.strip()


    if id_tingkat:
        mapel.id_tingkat = id_tingkat


    db.session.commit()


    return jsonify({"message": "Mapel diperbarui"}), 200



# =====================================================
# HAPUS MAPEL (ADMIN)
# =====================================================
@mapel_bp.route("/mapel/<int:id_mapel>", methods=["DELETE"])
@jwt_required()
def delete_mapel(id_mapel):

    claims = get_jwt()


    if claims["role"] != "admin":
        return jsonify({"message": "Hanya admin"}), 403


    mapel = MataPelajaran.query.get_or_404(id_mapel)


    # ================= CEK RELASI =================

    if mapel.kelas:
        return jsonify({
            "message": "Mapel masih dipakai di kelas"
        }), 409


    db.session.delete(mapel)
    db.session.commit()


    return jsonify({"message": "Mapel dihapus"}), 200



# =====================================================
# ASSIGN MAPEL KE KELAS
# =====================================================
@mapel_bp.route("/mapel/kelas/<int:id_kelas>", methods=["POST"])
@jwt_required()
def assign_mapel_kelas(id_kelas):

    claims = get_jwt()


    if claims["role"] != "admin":
        return jsonify({"message": "Hanya admin"}), 403


    data = request.json


    id_mapel = data.get("id_mapel")


    if not id_mapel:
        return jsonify({"message": "id_mapel wajib"}), 400


    kelas = Kelas.query.get_or_404(id_kelas)
    mapel = MataPelajaran.query.get_or_404(id_mapel)


    # ================= VALIDASI TINGKAT =================

    if kelas.id_tingkat != mapel.id_tingkat:
        return jsonify({
            "message": "Tingkat tidak sesuai"
        }), 400


    # ================= CEK DUPLIKAT =================

    if mapel in kelas.mapel:
        return jsonify({
            "message": "Mapel sudah ada"
        }), 409


    kelas.mapel.append(mapel)
    db.session.commit()  # ⬅️ pastikan commit di sini selesai
    return jsonify({"message": "Mapel ditambahkan"}), 201



# =====================================================
# HAPUS MAPEL DARI KELAS
# =====================================================
@mapel_bp.route("/mapel/kelas/<int:id_kelas>/<int:id_mapel>", methods=["DELETE"])
@jwt_required()
def remove_mapel_kelas(id_kelas, id_mapel):

    claims = get_jwt()


    if claims["role"] != "admin":
        return jsonify({"message": "Hanya admin"}), 403


    kelas = Kelas.query.get_or_404(id_kelas)
    mapel = MataPelajaran.query.get_or_404(id_mapel)


    if mapel not in kelas.mapel:
        return jsonify({
            "message": "Relasi tidak ada"
        }), 404


    kelas.mapel.remove(mapel)
    db.session.commit()


    return jsonify({"message": "Mapel dihapus dari kelas"}), 200

# =====================================================
# GET MAPEL PER KELAS
# =====================================================
@mapel_bp.route("/mapel/kelas/<int:id_kelas>", methods=["GET"])
@jwt_required()
def get_mapel_kelas(id_kelas):

    claims = get_jwt()

    # Optional: semua role boleh lihat, atau batasi
    if claims["role"] not in ["admin", "guru", "murid"]:
        return jsonify({"message": "Akses ditolak"}), 403

    status = (request.args.get("status") or "aktif").strip().lower()

    # Ambil data kelas
    kelas = Kelas.query.get_or_404(id_kelas)

    if status != "all" and str(getattr(kelas, "status", "aktif") or "aktif").strip().lower() != "aktif":
        return jsonify({
            "id_kelas": kelas.id_kelas,
            "nama_kelas": kelas.nama_kelas,
            "status_kelas": getattr(kelas, "status", "aktif"),
            "mapel": []
        }), 200

    jadwal_query = Jadwal.query.filter_by(id_kelas=id_kelas)
    if status != "all":
        jadwal_query = jadwal_query.filter(Jadwal.status == "aktif")

    rows = jadwal_query.all()
    mapel_ids_aktif = {j.id_mapel for j in rows if j.id_mapel}
    jumlah_jadwal_per_mapel = {}
    for j in rows:
        if not j.id_mapel:
            continue
        jumlah_jadwal_per_mapel[j.id_mapel] = jumlah_jadwal_per_mapel.get(j.id_mapel, 0) + 1

    mapel_list = []

    for mapel in kelas.mapel:
        if status != "all" and mapel.id_mapel not in mapel_ids_aktif:
            continue

        mapel_list.append({
            "id_mapel": mapel.id_mapel,
            "nama_mapel": mapel.nama_mapel,
            "id_tingkat": mapel.id_tingkat,
            "status_kelas": getattr(kelas, "status", "aktif"),
            "jumlah_jadwal_aktif": jumlah_jadwal_per_mapel.get(mapel.id_mapel, 0),
        })

    return jsonify({
        "id_kelas": kelas.id_kelas,
        "nama_kelas": kelas.nama_kelas,
        "status_kelas": getattr(kelas, "status", "aktif"),
        "mapel": mapel_list
    }), 200

    