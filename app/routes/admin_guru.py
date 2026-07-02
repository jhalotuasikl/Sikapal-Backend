from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, verify_jwt_in_request, get_jwt
from app import db
from app.models.guru import Guru
from app.models.user import User
from app.models.role import Role
import csv, io, random, string
from app.models.mata_pelajaran import MataPelajaran
from werkzeug.security import generate_password_hash

admin_guru_bp = Blueprint("admin_guru", __name__)


@admin_guru_bp.before_request
def _guard_admin_guru():
    if request.method == "OPTIONS":
        return None

    verify_jwt_in_request()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Akses khusus admin"}), 403

    return None

# ======================
# UTIL
# ======================
def generate_username(nama):
    base = nama.lower().replace(" ", "")
    while True:
        username = f"{base}{random.randint(100,999)}"
        if not User.query.filter_by(username=username).first():
            return username


def generate_password():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

@admin_guru_bp.route("/guru", methods=["POST"])
@jwt_required()
def tambah_guru():
    data = request.json

    if (
        not data or
        not data.get("nama_guru") or
        not data.get("nip")
    ):
        return jsonify({"message": "Data tidak lengkap"}), 400

    role = Role.query.filter_by(nama_role="guru").first()
    if not role:
        return jsonify({"message": "Role guru tidak ditemukan"}), 500

    if Guru.query.filter_by(nip=data["nip"]).first():
        return jsonify({"message": "NIP sudah terdaftar"}), 400

    username = generate_username(data["nama_guru"])
    password_asli = generate_password()
    password_hash = generate_password_hash(password_asli)

    try:
        user = User(
            username=username,
            password=password_hash,   # ✅ simpan hash
            id_role=role.id_role
        )
        db.session.add(user)
        db.session.flush()

        guru = Guru(
            nip=data["nip"],
            nama_guru=data["nama_guru"],
            id_user=user.id_user
        )
        db.session.add(guru)
        db.session.commit()

        return jsonify({
            "message": "Guru berhasil ditambahkan",
            "username": username,
            "password": password_asli   # ✅ kirim password asli ke admin
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": "Gagal menambahkan guru",
            "error": str(e)
        }), 500


@admin_guru_bp.route("/guru/import", methods=["POST"])
@jwt_required()
def import_guru_csv():

    if "file" not in request.files:
        return jsonify({"message": "File CSV tidak ditemukan"}), 400

    file = request.files["file"]

    if not file.filename.lower().endswith(".csv"):
        return jsonify({"message": "File harus CSV"}), 400

    raw = file.stream.read().decode("utf-8-sig")
    stream = io.StringIO(raw)

    first_line = raw.splitlines()[0] if raw.splitlines() else ""

    if ";" in first_line:
        delimiter = ";"
    elif "\t" in first_line:
        delimiter = "\t"
    else:
        delimiter = ","

    reader = csv.DictReader(stream, delimiter=delimiter)

    print("CSV DELIMITER:", delimiter)
    print("CSV HEADER:", reader.fieldnames)

    role = Role.query.filter_by(nama_role="guru").first()
    if not role:
        return jsonify({"message": "Role guru tidak ada"}), 500

    berhasil = 0
    gagal = []
    akun = []

    for i, row in enumerate(reader, start=2):
        print("ROW", i, ":", row)

        try:
            if not row.get("nip") or not row.get("nama_guru"):
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "Kolom wajib kosong"
                })
                continue

            nip = row["nip"].strip()
            nama = row["nama_guru"].strip()

            if Guru.query.filter_by(nip=nip).first():
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "NIP sudah ada"
                })
                continue

            username = generate_username(nama)
            password_asli = generate_password()
            password_hash = generate_password_hash(password_asli)

            user = User(
                username=username,
                password=password_hash,   # ✅ simpan hash
                id_role=role.id_role
            )
            db.session.add(user)
            db.session.flush()

            guru = Guru(
                nip=nip,
                nama_guru=nama,
                id_user=user.id_user
            )
            db.session.add(guru)

            berhasil += 1
            akun.append({
                "baris": i,
                "nip": nip,
                "nama_guru": nama,
                "username": username,
                "password": password_asli   # ✅ tampilkan yang asli ke admin
            })

        except Exception as e:
            print("IMPORT ERROR:", e)
            gagal.append({
                "baris": i,
                "row": row,
                "error": str(e)
            })

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": "Gagal commit import",
            "error": str(e)
        }), 500

    return jsonify({
        "message": "Import selesai",
        "berhasil": berhasil,
        "gagal": len(gagal),
        "akun": akun,
        "detail_gagal": gagal
    }), 201


# =====================================================
# LIST GURU
# =====================================================
@admin_guru_bp.route("/guru", methods=["GET"])
@jwt_required()
def list_guru():

    data = Guru.query.all()

    result = []

    for g in data:

        result.append({
            "id_guru": g.id_guru,
            "nip": g.nip,
            "nama_guru": g.nama_guru,
            "mapel": [
                {
                    "id_mapel": m.id_mapel,
                    "nama_mapel": m.nama_mapel
                } for m in g.mapel
            ]
        })

    return jsonify(result)


# =====================================================
# DETAIL + UPDATE
# =====================================================
@admin_guru_bp.route("/guru/<int:id_guru>", methods=["GET", "PUT"])
@jwt_required()
def update_guru(id_guru):
    guru = Guru.query.get_or_404(id_guru)

    if request.method == "GET":
        return jsonify({
            "id_guru": guru.id_guru,
            "nip": guru.nip,
            "nama_guru": guru.nama_guru,
            "id_mapel": [m.id_mapel for m in guru.mapel]
        }), 200

    data = request.json

    if not data:
        return jsonify({"message": "Data kosong"}), 400

    guru.nama_guru = data.get("nama_guru", guru.nama_guru)
    guru.nip = data.get("nip", guru.nip)

    db.session.commit()

    return jsonify({"message": "Guru berhasil diperbarui"}), 200


# =====================================================
# HAPUS
# =====================================================
@admin_guru_bp.route("/guru/<int:id_guru>", methods=["DELETE"])
@jwt_required()
def hapus_guru(id_guru):

    guru = Guru.query.get_or_404(id_guru)


    # hapus relasi
    guru.mapel.clear()


    if guru.user:
        db.session.delete(guru.user)


    db.session.delete(guru)
    db.session.commit()


    return jsonify({"message": "Guru berhasil dihapus"}), 200
