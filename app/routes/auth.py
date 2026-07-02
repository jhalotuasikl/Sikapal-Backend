from flask import Blueprint, request, jsonify, current_app

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)

from app import db

from app.models.user import User
from app.models.role import Role
from app.models.admin import Admin
from app.models.murid import Murid
from app.models.guru import Guru
from app.models.orang_tua_models import OrangTua

from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import os
import uuid
import secrets


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


auth_bp = Blueprint("auth", __name__)


def _get_user_role(user):
    role = Role.query.get(user.id_role)
    if not role:
        return None
    return role.nama_role.lower().strip()


def _is_user_active(user):
    status = getattr(user, "status", "aktif")
    status = str(status or "aktif").lower().strip()
    return status == "aktif"


def _is_current_user_admin():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return False, None, (jsonify({"message": "User tidak ditemukan"}), 404)

    if not _is_user_active(user):
        return False, user, (jsonify({"message": "Akun tidak aktif"}), 403)

    role_name = _get_user_role(user)

    if role_name != "admin":
        return False, user, (jsonify({"message": "Akses khusus admin"}), 403)

    return True, user, None


def _generate_temp_password():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "SIKAPAL-" + "".join(secrets.choice(alphabet) for _ in range(6))


def _truthy(value):
    if value is True:
        return True
    if value in (1, "1"):
        return True
    text = str(value or "").strip().lower()
    return text in {"true", "ya", "yes", "wajib", "1"}


def _user_display_data(user):
    role_name = _get_user_role(user) or "-"
    nama = user.username
    identitas = "-"
    id_ref = None

    if role_name == "admin":
        admin = Admin.query.filter_by(id_user=user.id_user).first()
        if admin:
            nama = admin.nama_admin
            identitas = "Administrator"
            id_ref = admin.id_admin

    elif role_name == "guru":
        guru = Guru.query.filter_by(id_user=user.id_user).first()
        if guru:
            nama = guru.nama_guru
            identitas = guru.nip or "-"
            id_ref = guru.id_guru

    elif role_name == "murid":
        murid = Murid.query.filter_by(id_user=user.id_user).first()
        if murid:
            nama = murid.nama_murid
            identitas = murid.nis or "-"
            id_ref = murid.id_murid

    elif role_name == "orang_tua":
        orang_tua = OrangTua.query.filter_by(id_user=user.id_user).first()
        if orang_tua:
            nama = orang_tua.nama_ortu
            identitas = orang_tua.no_hp or "Orang Tua"
            id_ref = orang_tua.id_ortu

    return {
        "id_user": user.id_user,
        "id_ref": id_ref,
        "username": user.username,
        "role": role_name,
        "nama": nama or user.username,
        "identitas": identitas,
        "status": getattr(user, "status", "aktif"),
        "must_change_password": _truthy(getattr(user, "must_change_password", False)),
    }


# =====================================================
# LOGIN
# =====================================================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json

    if not data:
        return jsonify({"message": "Data tidak lengkap"}), 400

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username / password kosong"}), 400

    user = User.query.filter_by(username=username).first()

    if not user:
        return jsonify({"message": "User tidak ditemukan"}), 401

    if not _is_user_active(user):
        return jsonify({"message": "Akun tidak aktif"}), 403

    if not check_password_hash(user.password, password):
        return jsonify({"message": "Password salah"}), 401

    role_name = _get_user_role(user)

    if not role_name:
        return jsonify({"message": "Role tidak valid"}), 500

    id_admin = None
    id_murid = None
    id_guru = None
    id_ortu = None

    nama_admin = None

    nama_murid = None
    nis = None

    nama_guru = None
    nip = None

    nama_ortu = None
    no_hp = None

    foto_profil_response = user.foto_profil

    if role_name == "admin":
        admin = Admin.query.filter_by(id_user=user.id_user).first()

        if admin:
            id_admin = admin.id_admin
            nama_admin = admin.nama_admin
        else:
            nama_admin = user.username or "Administrator"

        foto_profil_response = user.foto_profil

    elif role_name == "murid":
        murid = Murid.query.filter_by(id_user=user.id_user).first()

        if not murid:
            return jsonify({"message": "Data murid rusak"}), 500

        id_murid = murid.id_murid
        nama_murid = murid.nama_murid
        nis = murid.nis
        foto_profil_response = user.foto_profil

    elif role_name == "guru":
        guru = Guru.query.filter_by(id_user=user.id_user).first()

        if not guru:
            return jsonify({"message": "Data guru rusak"}), 500

        id_guru = guru.id_guru
        nama_guru = guru.nama_guru
        nip = guru.nip
        foto_profil_response = user.foto_profil

    elif role_name == "orang_tua":
        orang_tua = OrangTua.query.filter_by(id_user=user.id_user).first()

        if not orang_tua:
            return jsonify({"message": "Data orang tua rusak"}), 500

        id_ortu = orang_tua.id_ortu
        nama_ortu = orang_tua.nama_ortu
        no_hp = orang_tua.no_hp
        id_murid = orang_tua.id_murid

        murid = Murid.query.get(id_murid)

        if not murid:
            return jsonify({"message": "Data anak orang tua rusak"}), 500

        nama_murid = murid.nama_murid
        nis = murid.nis

        user_murid = User.query.get(murid.id_user)

        if user_murid:
            foto_profil_response = user_murid.foto_profil
        else:
            foto_profil_response = None

    access_token = create_access_token(
        identity=str(user.id_user),
        additional_claims={
            "role": role_name,
            "id_admin": id_admin,
            "id_guru": id_guru,
            "id_murid": id_murid,
            "id_ortu": id_ortu,
        },
    )

    refresh_token = create_refresh_token(
        identity=str(user.id_user),
    )

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,

        "id_user": user.id_user,
        "username": user.username,
        "role": role_name,
        "status": getattr(user, "status", None),
        "must_change_password": _truthy(getattr(user, "must_change_password", False)),

        "id_admin": id_admin,
        "id_guru": id_guru,
        "id_murid": id_murid,
        "id_ortu": id_ortu,

        "nama_admin": nama_admin,

        "nama_murid": nama_murid,
        "nis": nis,

        "nama_guru": nama_guru,
        "nip": nip,

        "nama_ortu": nama_ortu,
        "no_hp": no_hp,

        "foto_profil": foto_profil_response,
    }), 200


# =====================================================
# REFRESH TOKEN
# =====================================================
@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()

    user = User.query.get(user_id)

    if not user:
        return jsonify({"message": "User tidak ditemukan"}), 404

    if not _is_user_active(user):
        return jsonify({"message": "Akun tidak aktif"}), 403

    role_name = _get_user_role(user)

    if not role_name:
        return jsonify({"message": "Role tidak valid"}), 500

    id_admin = None
    id_guru = None
    id_murid = None
    id_ortu = None

    if role_name == "admin":
        admin = Admin.query.filter_by(id_user=user.id_user).first()
        if admin:
            id_admin = admin.id_admin

    elif role_name == "guru":
        guru = Guru.query.filter_by(id_user=user.id_user).first()
        if guru:
            id_guru = guru.id_guru

    elif role_name == "murid":
        murid = Murid.query.filter_by(id_user=user.id_user).first()
        if murid:
            id_murid = murid.id_murid

    elif role_name == "orang_tua":
        orang_tua = OrangTua.query.filter_by(id_user=user.id_user).first()
        if orang_tua:
            id_ortu = orang_tua.id_ortu
            id_murid = orang_tua.id_murid

    new_access = create_access_token(
        identity=str(user.id_user),
        additional_claims={
            "role": role_name,
            "id_admin": id_admin,
            "id_guru": id_guru,
            "id_murid": id_murid,
            "id_ortu": id_ortu,
        },
    )

    return jsonify({
        "access_token": new_access,
    }), 200


# =====================================================
# PROFILE
# =====================================================
@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"message": "User tidak ditemukan"}), 404

    role_name = _get_user_role(user)

    if not role_name:
        return jsonify({"message": "Role tidak valid"}), 500

    nama = user.username
    identitas = "-"

    id_admin = None
    id_murid = None
    id_guru = None
    id_ortu = None

    nama_admin = None

    nama_murid = None
    nis = None

    nama_guru = None
    nip = None

    nama_ortu = None
    no_hp = None

    foto_profil_response = user.foto_profil

    if role_name == "admin":
        admin = Admin.query.filter_by(id_user=user.id_user).first()

        if admin:
            id_admin = admin.id_admin
            nama_admin = admin.nama_admin
            nama = admin.nama_admin
        else:
            nama_admin = user.username or "Administrator"
            nama = nama_admin

        identitas = "Administrator"
        foto_profil_response = user.foto_profil

    elif role_name == "murid":
        murid = Murid.query.filter_by(id_user=user.id_user).first()

        if murid:
            id_murid = murid.id_murid
            nama_murid = murid.nama_murid
            nis = murid.nis

            nama = murid.nama_murid
            identitas = murid.nis
            foto_profil_response = user.foto_profil

    elif role_name == "guru":
        guru = Guru.query.filter_by(id_user=user.id_user).first()

        if guru:
            id_guru = guru.id_guru
            nama_guru = guru.nama_guru
            nip = guru.nip

            nama = guru.nama_guru
            identitas = guru.nip
            foto_profil_response = user.foto_profil

    elif role_name == "orang_tua":
        orang_tua = OrangTua.query.filter_by(id_user=user.id_user).first()

        if not orang_tua:
            return jsonify({"message": "Data orang tua rusak"}), 500

        id_ortu = orang_tua.id_ortu
        nama_ortu = orang_tua.nama_ortu
        no_hp = orang_tua.no_hp
        id_murid = orang_tua.id_murid

        nama = orang_tua.nama_ortu
        identitas = no_hp if no_hp else "Orang Tua"

        murid = Murid.query.get(id_murid)

        if not murid:
            return jsonify({"message": "Data anak orang tua rusak"}), 500

        nama_murid = murid.nama_murid
        nis = murid.nis

        user_murid = User.query.get(murid.id_user)

        if user_murid:
            foto_profil_response = user_murid.foto_profil
        else:
            foto_profil_response = None

    return jsonify({
        "id_user": user.id_user,
        "username": user.username,
        "role": role_name,
        "status": getattr(user, "status", None),
        "must_change_password": _truthy(getattr(user, "must_change_password", False)),

        "nama": nama,
        "identitas": identitas,

        "id_admin": id_admin,
        "id_guru": id_guru,
        "id_murid": id_murid,
        "id_ortu": id_ortu,

        "nama_admin": nama_admin,

        "nama_murid": nama_murid,
        "nis": nis,

        "nama_guru": nama_guru,
        "nip": nip,

        "nama_ortu": nama_ortu,
        "no_hp": no_hp,

        "foto_profil": foto_profil_response,
    }), 200


# =====================================================
# CHANGE PASSWORD
# =====================================================
@auth_bp.route("/change-password", methods=["PUT"])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"message": "User tidak ditemukan"}), 404

    data = request.json

    if not data:
        return jsonify({"message": "Data kosong"}), 400

    password_lama = data.get("password_lama")
    password_baru = data.get("password_baru")

    if not password_lama or not password_baru:
        return jsonify({"message": "Password lama dan password baru wajib diisi"}), 400

    if not check_password_hash(user.password, password_lama):
        return jsonify({"message": "Password lama salah"}), 400

    if len(password_baru) < 6:
        return jsonify({"message": "Password baru minimal 6 karakter"}), 400

    user.password = generate_password_hash(password_baru)
    user.must_change_password = False
    db.session.commit()

    return jsonify({
        "message": "Password berhasil diperbarui",
    }), 200




# =====================================================
# ADMIN RESET PASSWORD PENGGUNA
# =====================================================
@auth_bp.route("/admin/users/reset-password", methods=["GET"])
@jwt_required()
def admin_list_reset_password_users():
    is_admin, _admin_user, error = _is_current_user_admin()
    if not is_admin:
        return error

    q = (request.args.get("q") or "").strip().lower()
    role_filter = (request.args.get("role") or "all").strip().lower()
    role_filter = role_filter.replace(" ", "_")

    users = (
        User.query
        .join(Role, User.id_role == Role.id_role)
        .order_by(Role.nama_role.asc(), User.username.asc())
        .all()
    )

    result = []

    for user in users:
        row = _user_display_data(user)
        role_name = row["role"]

        if role_filter not in {"", "all", "semua"} and role_name != role_filter:
            continue

        searchable = " ".join([
            str(row.get("username") or ""),
            str(row.get("role") or ""),
            str(row.get("nama") or ""),
            str(row.get("identitas") or ""),
        ]).lower()

        if q and q not in searchable:
            continue

        result.append(row)

    return jsonify({
        "success": True,
        "total": len(result),
        "data": result,
    }), 200


@auth_bp.route("/admin/users/<int:id_user>/reset-password", methods=["PUT"])
@jwt_required()
def admin_reset_password_user(id_user):
    is_admin, admin_user, error = _is_current_user_admin()
    if not is_admin:
        return error

    user = User.query.get(id_user)

    if not user:
        return jsonify({"message": "User tidak ditemukan"}), 404

    data = request.get_json(silent=True) or {}
    password_baru = (data.get("password") or "").strip()

    if not password_baru:
        password_baru = _generate_temp_password()

    if len(password_baru) < 6:
        return jsonify({"message": "Password sementara minimal 6 karakter"}), 400

    try:
        user.password = generate_password_hash(password_baru)
        user.must_change_password = True
        db.session.commit()

        display = _user_display_data(user)

        return jsonify({
            "success": True,
            "message": "Password berhasil direset. Pengguna wajib mengganti password setelah login.",
            "id_user": user.id_user,
            "username": user.username,
            "role": display["role"],
            "nama": display["nama"],
            "temporary_password": password_baru,
            "must_change_password": True,
            "reset_by": admin_user.username,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": f"Gagal reset password: {str(e)}",
        }), 500


# =====================================================
# UPLOAD PHOTO
# =====================================================
@auth_bp.route("/upload-photo", methods=["PUT"])
@jwt_required()
def upload_photo():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"message": "User tidak ditemukan"}), 404

    role_name = _get_user_role(user)

    if not role_name:
        return jsonify({"message": "Role tidak valid"}), 500

    target_user = user

    if role_name == "orang_tua":
        orang_tua = OrangTua.query.filter_by(id_user=user.id_user).first()

        if not orang_tua:
            return jsonify({"message": "Data orang tua rusak"}), 500

        murid = Murid.query.get(orang_tua.id_murid)

        if not murid:
            return jsonify({"message": "Data anak orang tua rusak"}), 500

        user_murid = User.query.get(murid.id_user)

        if not user_murid:
            return jsonify({"message": "Akun murid tidak ditemukan"}), 500

        target_user = user_murid

    if "photo" not in request.files:
        return jsonify({"message": "File foto tidak ditemukan"}), 400

    file = request.files["photo"]

    if file.filename == "":
        return jsonify({"message": "Nama file kosong"}), 400

    if not allowed_file(file.filename):
        return jsonify({"message": "Format file harus png/jpg/jpeg/webp"}), 400

    upload_folder = os.path.join(
        current_app.root_path,
        "static",
        "profile_photos",
    )

    os.makedirs(upload_folder, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
    filepath = os.path.join(upload_folder, filename)

    try:
        if target_user.foto_profil:
            old_filename = os.path.basename(target_user.foto_profil)
            old_path = os.path.join(upload_folder, old_filename)

            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass

        file.save(filepath)

        if not os.path.exists(filepath):
            return jsonify({"message": "File gagal disimpan"}), 500

        if os.path.getsize(filepath) == 0:
            return jsonify({"message": "File kosong / rusak"}), 500

        target_user.foto_profil = f"/static/profile_photos/{filename}"
        db.session.commit()

        return jsonify({
            "message": "Foto profil berhasil diperbarui",
            "foto_profil": target_user.foto_profil,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": f"Gagal upload foto: {str(e)}",
        }), 500