from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, verify_jwt_in_request, get_jwt
from app import db

from app.models.murid import Murid
from app.models.user import User
from app.models.role import Role
from app.models.kelas import Kelas
from app.models.mata_pelajaran import MataPelajaran
from app.models.murid_tingkat import MuridTingkat
from app.models.kelas_mapel import kelas_mapel
from app.models.tingkat import Tingkat
from app.models.jadwal_murid import jadwal_murid
from app.models.orang_tua_models import OrangTua

from werkzeug.security import generate_password_hash
from app.utils.jadwal_helper import sinkron_jadwal_murid

from sqlalchemy import select
import csv
import io
import random
import string


admin_murid_bp = Blueprint("admin_murid", __name__)


@admin_murid_bp.before_request
def _guard_admin_murid():
    if request.method == "OPTIONS":
        return None

    verify_jwt_in_request()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Akses khusus admin"}), 403

    return None


# ======================
# GENERATOR AKUN
# ======================
def generate_password():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


def username_murid_from_nis(nis):
    return str(nis).strip()


def username_ortu_from_nis(nis):
    return f"ort_{str(nis).strip()}"


def nama_ortu_default(nama_murid):
    return f"Orang Tua {nama_murid}"


def get_role_or_error(nama_role):
    role = Role.query.filter_by(nama_role=nama_role).first()
    return role


def buat_user_aktif(username, password_asli, id_role):
    """
    Buat akun user untuk murid/orang tua.
    Jika model User punya kolom status, status langsung dibuat aktif
    agar akun bisa login di auth.py.
    """
    user = User(
        username=username,
        password=generate_password_hash(password_asli),
        id_role=id_role
    )

    if hasattr(User, "status"):
        user.status = "aktif"

    return user


def get_daftar_id_mapel_by_kelas(id_kelas):
    return db.session.execute(
        select(kelas_mapel.c.id_mapel).where(
            kelas_mapel.c.id_kelas == id_kelas
        )
    ).scalars().all()


def build_akun_payload(
    murid,
    kelas,
    username_murid,
    password_murid,
    username_orang_tua,
    password_orang_tua,
    baris=None,
    catatan=None
):
    payload = {
        "nis": murid.nis,
        "nama_murid": murid.nama_murid,
        "id_kelas": kelas.id_kelas if kelas else None,
        "nama_kelas": kelas.nama_kelas if kelas else "-",
        "kelas": kelas.nama_kelas if kelas else "-",

        "username": username_murid,
        "password": password_murid,

        "username_murid": username_murid,
        "password_murid": password_murid,

        "username_orang_tua": username_orang_tua,
        "username_ortu": username_orang_tua,
        "password_orang_tua": password_orang_tua,
        "password_ortu": password_orang_tua,
    }

    if baris is not None:
        payload["baris"] = baris

    if catatan:
        payload["catatan"] = catatan
        payload["warning"] = catatan

    return payload


# =====================================================
# TAMBAH MURID MANUAL
# =====================================================
@admin_murid_bp.route("/murid", methods=["POST"])
@jwt_required()
def tambah_murid_manual():
    data = request.json or {}
    print("DATA MASUK:", data)

    if (
        not data.get("nis") or
        not data.get("nama_murid") or
        not data.get("id_kelas") or
        not data.get("id_tingkat")
    ):
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400

    nis = str(data["nis"]).strip()
    nama_murid = str(data["nama_murid"]).strip()
    id_kelas = data["id_kelas"]
    id_tingkat = data["id_tingkat"]

    tingkat = Tingkat.query.get(id_tingkat)
    if not tingkat:
        return jsonify({"success": False, "message": "Tingkat tidak ditemukan"}), 404

    kelas = Kelas.query.filter_by(id_kelas=id_kelas).first()
    if not kelas:
        return jsonify({"success": False, "message": "Kelas tidak ditemukan"}), 404

    if Murid.query.filter_by(nis=nis).first():
        return jsonify({"success": False, "message": "NIS sudah terdaftar"}), 400

    role_murid = get_role_or_error("murid")
    if not role_murid:
        return jsonify({"success": False, "message": "Role murid tidak ada"}), 500

    role_ortu = get_role_or_error("orang_tua")
    if not role_ortu:
        return jsonify({"success": False, "message": "Role orang_tua tidak ada"}), 500

    username_murid = username_murid_from_nis(nis)
    username_orang_tua = username_ortu_from_nis(nis)

    if User.query.filter_by(username=username_murid).first():
        return jsonify({
            "success": False,
            "message": "Username/NIS murid sudah digunakan"
        }), 400

    if User.query.filter_by(username=username_orang_tua).first():
        return jsonify({
            "success": False,
            "message": "Username orang tua sudah digunakan"
        }), 400

    daftar_id_mapel = get_daftar_id_mapel_by_kelas(kelas.id_kelas)
    warning_mapel = None

    # Jangan gagalkan tambah murid hanya karena kelas belum punya mapel.
    # Murid tetap disimpan, nanti saat mapel/jadwal dibuat bisa disinkronkan.
    if not daftar_id_mapel:
        warning_mapel = (
            "Kelas belum memiliki mata pelajaran. Murid tetap disimpan, "
            "tetapi belum otomatis terhubung ke jadwal/mapel."
        )

    password_murid_asli = generate_password()
    password_ortu_asli = generate_password()

    try:
        user_murid = buat_user_aktif(
            username=username_murid,
            password_asli=password_murid_asli,
            id_role=role_murid.id_role
        )
        db.session.add(user_murid)
        db.session.flush()

        murid = Murid(
            nis=nis,
            nama_murid=nama_murid,
            id_kelas=kelas.id_kelas,
            id_user=user_murid.id_user
        )
        db.session.add(murid)
        db.session.flush()

        mt = MuridTingkat(
            id_murid=murid.id_murid,
            id_tingkat=id_tingkat,
            id_kelas=kelas.id_kelas,
            tahun_ajaran=data.get(
                "tahun_ajaran",
                getattr(kelas, "tahun_ajaran", "2025/2026")
            ),
            status="aktif"
        )
        db.session.add(mt)

        for idm in daftar_id_mapel:
            mapel = MataPelajaran.query.get(idm)

            if not mapel:
                db.session.rollback()
                return jsonify({
                    "success": False,
                    "message": f"Mapel ID {idm} tidak ditemukan"
                }), 404

            if mapel not in murid.mapel:
                murid.mapel.append(mapel)

        if daftar_id_mapel:
            sinkron_jadwal_murid(
                id_murid=murid.id_murid,
                id_kelas=kelas.id_kelas,
                daftar_id_mapel=daftar_id_mapel
            )

        user_ortu = buat_user_aktif(
            username=username_orang_tua,
            password_asli=password_ortu_asli,
            id_role=role_ortu.id_role
        )
        db.session.add(user_ortu)
        db.session.flush()

        orang_tua = OrangTua(
            nama_ortu=data.get("nama_ortu") or nama_ortu_default(nama_murid),
            no_hp=data.get("no_hp"),
            id_murid=murid.id_murid,
            id_user=user_ortu.id_user
        )
        db.session.add(orang_tua)

        db.session.commit()

        akun_payload = build_akun_payload(
            murid=murid,
            kelas=kelas,
            username_murid=username_murid,
            password_murid=password_murid_asli,
            username_orang_tua=username_orang_tua,
            password_orang_tua=password_ortu_asli,
            catatan=warning_mapel
        )

        return jsonify({
            "success": True,
            "message": "Murid, akun murid, dan akun orang tua berhasil ditambahkan",
            "warning": warning_mapel,

            "username": username_murid,
            "password": password_murid_asli,

            "username_murid": username_murid,
            "password_murid": password_murid_asli,
            "username_orang_tua": username_orang_tua,
            "username_ortu": username_orang_tua,
            "password_orang_tua": password_ortu_asli,
            "password_ortu": password_ortu_asli,

            "data": akun_payload,
            "akun": [akun_payload]
        }), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": "Gagal menambahkan murid",
            "error": str(e)
        }), 500


# =====================================================
# IMPORT CSV
# =====================================================
@admin_murid_bp.route("/murid/import", methods=["POST"])
@jwt_required()
def import_murid_csv():

    if "file" not in request.files:
        return jsonify({"message": "File CSV tidak ditemukan"}), 400

    file = request.files["file"]

    if not file.filename.lower().endswith(".csv"):
        return jsonify({"message": "File harus CSV"}), 400

    raw = file.stream.read().decode("utf-8-sig")
    stream = io.StringIO(raw)

    lines = raw.splitlines()
    first_line = lines[0] if lines else ""

    if ";" in first_line:
        delimiter = ";"
    elif "\t" in first_line:
        delimiter = "\t"
    else:
        delimiter = ","

    reader = csv.DictReader(stream, delimiter=delimiter)

    print("CSV DELIMITER:", delimiter)
    print("CSV HEADER:", reader.fieldnames)

    role_murid = get_role_or_error("murid")
    if not role_murid:
        return jsonify({"message": "Role murid tidak ada"}), 500

    role_ortu = get_role_or_error("orang_tua")
    if not role_ortu:
        return jsonify({"message": "Role orang_tua tidak ada"}), 500

    berhasil = 0
    gagal = []
    akun = []
    peringatan = []

    for i, row in enumerate(reader, start=2):
        try:
            if not row.get("nis") or not row.get("nama_murid") or not row.get("id_kelas"):
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "Kolom wajib kosong"
                })
                continue

            nis = str(row["nis"]).strip()
            nama_murid = str(row["nama_murid"]).strip()

            if Murid.query.filter_by(nis=nis).first():
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "NIS sudah ada"
                })
                continue

            try:
                id_kelas = int(str(row["id_kelas"]).strip())
            except Exception:
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "ID kelas bukan angka"
                })
                continue

            kelas = Kelas.query.get(id_kelas)
            if not kelas:
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "Kelas tidak ditemukan"
                })
                continue

            daftar_id_mapel = get_daftar_id_mapel_by_kelas(kelas.id_kelas)
            warning_mapel = None

            # Kelas tanpa mapel tidak lagi membuat import gagal.
            # Data murid + akun tetap dibuat, hanya sinkron mapel/jadwal dilewati.
            if not daftar_id_mapel:
                warning_mapel = (
                    "Kelas belum memiliki mata pelajaran. Murid tetap disimpan, "
                    "tetapi belum otomatis terhubung ke jadwal/mapel."
                )
                peringatan.append({
                    "baris": i,
                    "row": row,
                    "warning": warning_mapel
                })

            username_murid = username_murid_from_nis(nis)
            username_orang_tua = username_ortu_from_nis(nis)

            if User.query.filter_by(username=username_murid).first():
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "Username/NIS murid sudah digunakan"
                })
                continue

            if User.query.filter_by(username=username_orang_tua).first():
                gagal.append({
                    "baris": i,
                    "row": row,
                    "error": "Username orang tua sudah digunakan"
                })
                continue

            password_murid_asli = generate_password()
            password_ortu_asli = generate_password()

            user_murid = buat_user_aktif(
                username=username_murid,
                password_asli=password_murid_asli,
                id_role=role_murid.id_role
            )
            db.session.add(user_murid)
            db.session.flush()

            murid = Murid(
                nis=nis,
                nama_murid=nama_murid,
                id_kelas=kelas.id_kelas,
                id_user=user_murid.id_user
            )
            db.session.add(murid)
            db.session.flush()

            mt = MuridTingkat(
                id_murid=murid.id_murid,
                id_tingkat=kelas.id_tingkat,
                id_kelas=kelas.id_kelas,
                tahun_ajaran=getattr(kelas, "tahun_ajaran", "2025/2026"),
                status="aktif"
            )
            db.session.add(mt)

            for idm in daftar_id_mapel:
                mapel = MataPelajaran.query.get(idm)

                if not mapel:
                    raise Exception(f"Mapel ID {idm} tidak ditemukan")

                if mapel not in murid.mapel:
                    murid.mapel.append(mapel)

            if daftar_id_mapel:
                sinkron_jadwal_murid(
                    id_murid=murid.id_murid,
                    id_kelas=kelas.id_kelas,
                    daftar_id_mapel=daftar_id_mapel
                )

            user_ortu = buat_user_aktif(
                username=username_orang_tua,
                password_asli=password_ortu_asli,
                id_role=role_ortu.id_role
            )
            db.session.add(user_ortu)
            db.session.flush()

            orang_tua = OrangTua(
                nama_ortu=row.get("nama_ortu") or nama_ortu_default(nama_murid),
                no_hp=row.get("no_hp"),
                id_murid=murid.id_murid,
                id_user=user_ortu.id_user
            )
            db.session.add(orang_tua)

            db.session.commit()

            berhasil += 1

            akun.append(
                build_akun_payload(
                    murid=murid,
                    kelas=kelas,
                    username_murid=username_murid,
                    password_murid=password_murid_asli,
                    username_orang_tua=username_orang_tua,
                    password_orang_tua=password_ortu_asli,
                    baris=i,
                    catatan=warning_mapel
                )
            )

        except Exception as e:
            db.session.rollback()
            gagal.append({
                "baris": i,
                "row": row,
                "error": str(e)
            })

    return jsonify({
        "message": "Import selesai",
        "berhasil": berhasil,
        "gagal": len(gagal),
        "akun": akun,
        "detail_gagal": gagal,
        "peringatan": peringatan
    }), 201


# =====================================================
# UPDATE
# =====================================================
@admin_murid_bp.route("/murid/<int:id_murid>", methods=["PUT"])
@jwt_required()
def update_murid(id_murid):

    data = request.json

    if not data:
        return jsonify({"message": "Data kosong"}), 400

    murid = Murid.query.get_or_404(id_murid)

    if "nis" in data:
        nis_baru = str(data["nis"]).strip()

        if Murid.query.filter(
            Murid.nis == nis_baru,
            Murid.id_murid != id_murid
        ).first():
            return jsonify({"message": "NIS sudah digunakan"}), 400

        user_murid = User.query.get(murid.id_user)
        username_murid_baru = username_murid_from_nis(nis_baru)
        username_ortu_baru = username_ortu_from_nis(nis_baru)

        if User.query.filter(
            User.username == username_murid_baru,
            User.id_user != murid.id_user
        ).first():
            return jsonify({"message": "Username/NIS murid sudah digunakan"}), 400

        orang_tua_list = OrangTua.query.filter_by(id_murid=murid.id_murid).all()

        for ot in orang_tua_list:
            if User.query.filter(
                User.username == username_ortu_baru,
                User.id_user != ot.id_user
            ).first():
                return jsonify({"message": "Username orang tua sudah digunakan"}), 400

        murid.nis = nis_baru

        if user_murid:
            user_murid.username = username_murid_baru

        for ot in orang_tua_list:
            user_ortu = User.query.get(ot.id_user)
            if user_ortu:
                user_ortu.username = username_ortu_baru

    murid.nama_murid = data.get("nama_murid", murid.nama_murid)

    if "id_kelas" in data:
        kelas = Kelas.query.get(data["id_kelas"])
        if not kelas:
            return jsonify({"message": "Kelas tidak ditemukan"}), 404

        mt = MuridTingkat.query.filter_by(
            id_murid=murid.id_murid,
            status="aktif"
        ).first()

        # Edit murid hanya untuk koreksi/pindah kelas pada tahun ajaran yang sama.
        # Jika tahun ajaran berbeda, gunakan fitur Kenaikan Kelas agar riwayat lama tidak tertimpa.
        if mt and mt.tahun_ajaran and kelas.tahun_ajaran and mt.tahun_ajaran != kelas.tahun_ajaran:
            return jsonify({
                "message": "Kelas tujuan berbeda tahun ajaran. Gunakan menu Kenaikan Kelas agar riwayat murid tetap aman."
            }), 400

        murid.id_kelas = kelas.id_kelas

        if mt:
            mt.id_kelas = kelas.id_kelas
            mt.id_tingkat = kelas.id_tingkat
            mt.tahun_ajaran = mt.tahun_ajaran or getattr(kelas, "tahun_ajaran", None)
        else:
            mt = MuridTingkat(
                id_murid=murid.id_murid,
                id_tingkat=kelas.id_tingkat,
                id_kelas=kelas.id_kelas,
                tahun_ajaran=getattr(kelas, "tahun_ajaran", "2025/2026"),
                status="aktif"
            )
            db.session.add(mt)

        murid.mapel.clear()

        daftar_id_mapel = get_daftar_id_mapel_by_kelas(kelas.id_kelas)

        for idm in daftar_id_mapel:
            mapel = MataPelajaran.query.get(idm)

            if not mapel:
                return jsonify({
                    "message": f"Mapel ID {idm} tidak ditemukan"
                }), 404

            murid.mapel.append(mapel)

        sinkron_jadwal_murid(
            id_murid=murid.id_murid,
            id_kelas=kelas.id_kelas,
            daftar_id_mapel=daftar_id_mapel
        )

    if "id_mapel" in data:
        murid.mapel.clear()

        for idm in data["id_mapel"]:
            mapel = MataPelajaran.query.get(idm)

            if not mapel:
                return jsonify({
                    "message": f"Mapel ID {idm} tidak ditemukan"
                }), 404

            murid.mapel.append(mapel)

    db.session.commit()

    return jsonify({"message": "Murid diperbarui"}), 200


# =====================================================
# DELETE
# =====================================================
@admin_murid_bp.route("/murid/<int:id_murid>", methods=["DELETE"])
@jwt_required()
def hapus_murid(id_murid):

    murid = Murid.query.get_or_404(id_murid)

    orang_tua_list = OrangTua.query.filter_by(id_murid=id_murid).all()

    for ot in orang_tua_list:
        user_ortu = User.query.get(ot.id_user)

        db.session.delete(ot)

        if user_ortu:
            db.session.delete(user_ortu)

    MuridTingkat.query.filter_by(id_murid=id_murid).delete()

    try:
        db.session.execute(
            jadwal_murid.delete().where(
                jadwal_murid.c.id_murid == id_murid
            )
        )
    except Exception:
        pass

    murid.mapel.clear()

    user_murid = User.query.get(murid.id_user)

    db.session.delete(murid)

    if user_murid:
        db.session.delete(user_murid)

    db.session.commit()

    return jsonify({"message": "Murid dan akun orang tua berhasil dihapus"}), 200


# =====================================================
# LIST BY TINGKAT
# =====================================================
@admin_murid_bp.route("/murid/tingkat/<int:id_tingkat>", methods=["GET"])
@jwt_required()
def list_murid_by_tingkat(id_tingkat):

    murids = (
        Murid.query
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .filter(
            MuridTingkat.id_tingkat == id_tingkat,
            MuridTingkat.status == "aktif"
        )
        .all()
    )

    tingkat = Tingkat.query.get(id_tingkat)
    pangkat = tingkat.pangkat if tingkat else None

    result = []

    for m in murids:
        mapel_list = [
            {
                "id_mapel": mapel.id_mapel,
                "nama_mapel": mapel.nama_mapel,
            }
            for mapel in m.mapel
        ]

        # Penting: return 1 baris untuk 1 murid.
        # Jangan loop result per mapel karena itu membuat card murid duplikat
        # saat filter tingkat di Flutter.
        result.append({
            "id_murid": m.id_murid,
            "nis": m.nis,
            "nama_murid": m.nama_murid,

            "id_kelas": m.id_kelas,
            "kelas": m.kelas.nama_kelas if m.kelas else "-",

            "id_tingkat": id_tingkat,
            "pangkat": pangkat,
            "tahun_ajaran": getattr(m.kelas, "tahun_ajaran", None) if m.kelas else None,
            "status": "aktif",

            "jumlah_mapel": len(mapel_list),
            "mapel_list": mapel_list,
        })

    return jsonify(result), 200


# =====================================================
# LIST ALL
# =====================================================
@admin_murid_bp.route("/murid", methods=["GET"])
@jwt_required()
def list_murid():
    try:
        # Default hanya murid pada kelas aktif. Gunakan ?status=all untuk halaman riwayat/khusus.
        status = (request.args.get("status") or "aktif").strip().lower()
        murids = Murid.query.order_by(Murid.nama_murid.asc()).all()
        result = []

        for m in murids:
            mt = MuridTingkat.query.filter_by(
                id_murid=m.id_murid,
                status="aktif"
            ).first()

            kelas_aktif = Kelas.query.get(mt.id_kelas) if mt else None

            if status != "all":
                if not mt or not kelas_aktif:
                    continue
                if str(getattr(kelas_aktif, "status", "aktif") or "aktif").strip().lower() != "aktif":
                    continue

            tingkat_id = None
            pangkat = None

            if mt:
                tingkat_id = mt.id_tingkat
                tingkat = Tingkat.query.get(mt.id_tingkat)

                if tingkat:
                    pangkat = tingkat.pangkat

            orang_tua = OrangTua.query.filter_by(id_murid=m.id_murid).first()
            username_orang_tua = None

            if orang_tua:
                user_ortu = User.query.get(orang_tua.id_user)
                username_orang_tua = user_ortu.username if user_ortu else None

            kelas_display = kelas_aktif or m.kelas

            result.append({
                "id_murid": m.id_murid,
                "nis": m.nis,
                "nama_murid": m.nama_murid,
                "id_kelas": mt.id_kelas if mt else m.id_kelas,
                "kelas": kelas_display.nama_kelas if kelas_display else "-",
                "status_kelas": getattr(kelas_display, "status", None) if kelas_display else None,
                "id_tingkat": tingkat_id,
                "pangkat": pangkat,
                "tahun_ajaran": mt.tahun_ajaran if mt else None,
                "status": mt.status if mt else None,

                "id_ortu": orang_tua.id_ortu if orang_tua else None,
                "nama_ortu": orang_tua.nama_ortu if orang_tua else None,
                "no_hp_ortu": orang_tua.no_hp if orang_tua else None,
                "username_orang_tua": username_orang_tua,
            })

        return jsonify(result), 200

    except Exception as e:
        print("❌ ERROR list_murid:", e)
        return jsonify({"error": str(e)}), 500

# Endpoint khusus murid dipindahkan ke app/routes/murid.py.
