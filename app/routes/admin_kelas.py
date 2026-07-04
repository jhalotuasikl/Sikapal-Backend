from flask import Blueprint, request, jsonify
from app import db
from app.models.kelas import Kelas
from app.models.tingkat import Tingkat
from flask_jwt_extended import jwt_required, get_jwt, verify_jwt_in_request
from app.models.jadwal import Jadwal
from app.models.murid_tingkat import MuridTingkat
from app.models.mata_pelajaran import MataPelajaran
from app.models.kelas_mapel import kelas_mapel
from app.models.periode_akademik import PeriodeAkademik
from app.utils.jadwal_helper import sinkron_jadwal_murid
from sqlalchemy import select

admin_kelas_bp = Blueprint("admin_kelas", __name__)


@admin_kelas_bp.before_request
def _guard_admin_kelas():
    if request.method == "OPTIONS":
        return None

    verify_jwt_in_request()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Akses khusus admin"}), 403

    return None


def _is_admin():
    claims = get_jwt()
    return claims.get("role") == "admin"


def _status_value(obj, default="aktif"):
    return getattr(obj, "status", None) or default


def _is_status_aktif(value):
    return str(value or "aktif").strip().lower() == "aktif"


def _jadwal_payload(j):
    mapel = getattr(j, "mapel", None)
    return {
        "id_jadwal": j.id_jadwal,
        "id_kelas": j.id_kelas,
        "id_mapel": j.id_mapel,
        "nama_mapel": mapel.nama_mapel if mapel else None,
        "mapel": mapel.nama_mapel if mapel else None,
        "hari": j.hari,
        "mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
        "selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
        "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
        "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
        "status": _status_value(j),
    }


def _mapel_payload(m):
    return {
        "id_mapel": m.id_mapel,
        "nama_mapel": m.nama_mapel,
        "mapel": m.nama_mapel,
        "id_tingkat": m.id_tingkat,
    }




def _murid_riwayat_kelas_payload(kelas):
    """
    Ambil daftar murid yang pernah berada pada kelas ini berdasarkan tabel MuridTingkat.
    Ini penting untuk kelas arsip, karena Murid.id_kelas biasanya sudah pindah ke kelas aktif baru.
    """
    from app.models.murid import Murid

    rows = (
        db.session.query(MuridTingkat, Murid)
        .join(Murid, MuridTingkat.id_murid == Murid.id_murid)
        .filter(MuridTingkat.id_kelas == kelas.id_kelas)
        .order_by(Murid.nama_murid.asc())
        .all()
    )

    hasil = []
    sudah = set()

    for mt, murid in rows:
        if murid.id_murid in sudah:
            continue

        sudah.add(murid.id_murid)
        hasil.append({
            "id_murid": murid.id_murid,
            "nis": getattr(murid, "nis", None),
            "nama_murid": murid.nama_murid,
            "id_kelas": mt.id_kelas,
            "id_tingkat": mt.id_tingkat,
            "tahun_ajaran": mt.tahun_ajaran,
            "status_riwayat": mt.status,
        })

    # Fallback untuk kelas aktif/lama yang mungkin belum punya row MuridTingkat.
    if not hasil:
        murid_aktif = Murid.query.filter_by(id_kelas=kelas.id_kelas).order_by(Murid.nama_murid.asc()).all()
        hasil = [
            {
                "id_murid": m.id_murid,
                "nis": getattr(m, "nis", None),
                "nama_murid": m.nama_murid,
                "id_kelas": kelas.id_kelas,
                "id_tingkat": kelas.id_tingkat,
                "tahun_ajaran": kelas.tahun_ajaran,
                "status_riwayat": _status_value(kelas),
            }
            for m in murid_aktif
        ]

    return hasil


def _murid_aktif_kelas_payload(kelas):
    """Murid yang masih aktif pada kelas ini. Dipakai halaman selain riwayat/promosi."""
    from app.models.murid import Murid

    if not _is_status_aktif(_status_value(kelas)):
        return []

    rows = (
        db.session.query(MuridTingkat, Murid)
        .join(Murid, MuridTingkat.id_murid == Murid.id_murid)
        .filter(
            MuridTingkat.id_kelas == kelas.id_kelas,
            MuridTingkat.status == "aktif",
        )
        .order_by(Murid.nama_murid.asc())
        .all()
    )

    hasil = [
        {
            "id_murid": murid.id_murid,
            "nis": getattr(murid, "nis", None),
            "nama_murid": murid.nama_murid,
            "id_kelas": mt.id_kelas,
            "id_tingkat": mt.id_tingkat,
            "tahun_ajaran": mt.tahun_ajaran,
            "status": mt.status,
            "status_riwayat": mt.status,
        }
        for mt, murid in rows
    ]

    if hasil:
        return hasil

    # Fallback untuk data lama yang belum punya MuridTingkat.
    murid_aktif = Murid.query.filter_by(id_kelas=kelas.id_kelas).order_by(Murid.nama_murid.asc()).all()
    return [
        {
            "id_murid": m.id_murid,
            "nis": getattr(m, "nis", None),
            "nama_murid": m.nama_murid,
            "id_kelas": kelas.id_kelas,
            "id_tingkat": kelas.id_tingkat,
            "tahun_ajaran": kelas.tahun_ajaran,
            "status": _status_value(kelas),
            "status_riwayat": _status_value(kelas),
        }
        for m in murid_aktif
    ]


def _kelas_payload(k, include_detail=False, include_selesai_detail=False):
    tingkat = getattr(k, "tingkat", None)

    payload = {
        "id_kelas": k.id_kelas,
        "nama_kelas": k.nama_kelas,
        "kelas": k.nama_kelas,
        "tahun_ajaran": k.tahun_ajaran,
        "id_tingkat": k.id_tingkat,
        "pangkat": tingkat.pangkat if tingkat else None,
        "status": _status_value(k),
        "tingkat": {
            "id_tingkat": tingkat.id_tingkat if tingkat else k.id_tingkat,
            "pangkat": tingkat.pangkat if tingkat else None,
        },
    }

    if include_detail:
        jadwal_query = Jadwal.query.filter_by(id_kelas=k.id_kelas)

        if not include_selesai_detail:
            if not _is_status_aktif(_status_value(k)):
                payload["mapel"] = []
                payload["jadwal"] = []
                payload["murid"] = []
                payload["jumlah_murid"] = 0
                return payload

            jadwal_query = jadwal_query.filter(Jadwal.status == "aktif")

        jadwal_list = jadwal_query.order_by(
            Jadwal.hari.asc(), Jadwal.jam_mulai.asc()
        ).all()
        payload["jadwal"] = [_jadwal_payload(j) for j in jadwal_list]

        try:
            if include_selesai_detail:
                payload["mapel"] = [_mapel_payload(m) for m in k.mapel.all()]
            else:
                mapel_ids_aktif = {j.id_mapel for j in jadwal_list if j.id_mapel}
                payload["mapel"] = [
                    _mapel_payload(m)
                    for m in k.mapel.all()
                    if m.id_mapel in mapel_ids_aktif
                ]
        except Exception:
            payload["mapel"] = []

        payload["murid"] = (
            _murid_riwayat_kelas_payload(k)
            if include_selesai_detail
            else _murid_aktif_kelas_payload(k)
        )
        payload["jumlah_murid"] = len(payload["murid"])
    else:
        jadwal_list = []
        if _is_status_aktif(_status_value(k)):
            jadwal_list = Jadwal.query.filter_by(id_kelas=k.id_kelas, status="aktif").order_by(
                Jadwal.hari.asc(), Jadwal.jam_mulai.asc()
            ).all()
        payload["jadwal"] = [_jadwal_payload(j) for j in jadwal_list]

    return payload


def _arsipkan_kelas_jika_kosong(id_kelas):
    if not id_kelas:
        return

    kelas = Kelas.query.get(id_kelas)
    if not kelas:
        return

    masih_aktif = MuridTingkat.query.filter_by(
        id_kelas=id_kelas,
        status="aktif"
    ).first()

    if masih_aktif:
        return

    kelas.status = "selesai"
    Jadwal.query.filter_by(id_kelas=id_kelas).update({"status": "selesai"})


# === ROUTE: GET LIST KELAS ===
@admin_kelas_bp.route("/kelas", methods=["GET"])
@jwt_required()
def list_kelas():
    # default hanya kelas aktif agar dropdown utama tidak penuh.
    # gunakan ?status=all untuk semua, atau ?status=selesai untuk arsip.
    status = (request.args.get("status") or "aktif").lower().strip()

    query = Kelas.query

    if status != "all":
        query = query.filter(Kelas.status == status)

    kelas_list = query.order_by(Kelas.id_tingkat.asc(), Kelas.nama_kelas.asc()).all()

    return jsonify([_kelas_payload(k) for k in kelas_list]), 200


# === ROUTE: RIWAYAT / ARSIP KELAS ===
@admin_kelas_bp.route("/kelas/riwayat", methods=["GET"])
@jwt_required()
def riwayat_kelas():
    if not _is_admin():
        return jsonify({"message": "Hanya admin"}), 403

    status = (request.args.get("status") or "selesai").lower().strip()
    tahun_ajaran = request.args.get("tahun_ajaran")
    id_tingkat = request.args.get("id_tingkat")
    q = request.args.get("q")

    query = Kelas.query

    if status == "all":
        query = query.filter(Kelas.status != "aktif")
    else:
        query = query.filter(Kelas.status == status)

    if tahun_ajaran:
        query = query.filter(Kelas.tahun_ajaran == tahun_ajaran)

    if id_tingkat:
        query = query.filter(Kelas.id_tingkat == id_tingkat)

    if q:
        like = f"%{q}%"
        query = query.filter(Kelas.nama_kelas.ilike(like))

    kelas_list = query.order_by(
        Kelas.tahun_ajaran.desc(),
        Kelas.id_tingkat.asc(),
        Kelas.nama_kelas.asc(),
    ).all()

    return jsonify([_kelas_payload(k, include_detail=True, include_selesai_detail=True) for k in kelas_list]), 200


# === ROUTE: TAMBAH KELAS ===
@admin_kelas_bp.route("/kelas", methods=["POST"])
@jwt_required()
def tambah_kelas():
    if not _is_admin():
        return jsonify({"message": "Hanya admin yang boleh menambah kelas"}), 403

    data = request.json or {}
    nama_kelas = (data.get("nama_kelas") or "").strip()
    periode_aktif = PeriodeAkademik.aktif()
    tahun_ajaran = (periode_aktif.tahun_ajaran if periode_aktif else (data.get("tahun_ajaran") or "")).strip()
    id_tingkat = data.get("id_tingkat")

    if not periode_aktif:
        return jsonify({"message": "Periode akademik aktif belum diatur"}), 400

    if not nama_kelas or not tahun_ajaran or not id_tingkat:
        return jsonify({"message": "Nama kelas, tingkat, dan periode akademik aktif wajib ada"}), 400

    tingkat = Tingkat.query.get(id_tingkat)
    if not tingkat:
        return jsonify({"message": "Tingkat tidak ditemukan"}), 404

    kelas_sudah_ada = Kelas.query.filter_by(
        nama_kelas=nama_kelas,
        tahun_ajaran=tahun_ajaran,
        id_tingkat=id_tingkat,
        status="aktif",
    ).first()

    if kelas_sudah_ada:
        return jsonify({"message": "Kelas aktif dengan tingkat dan tahun ajaran tersebut sudah ada"}), 409

    kelas = Kelas(
        nama_kelas=nama_kelas,
        tahun_ajaran=tahun_ajaran,
        id_tingkat=id_tingkat,
        status="aktif",
    )
    db.session.add(kelas)
    db.session.commit()

    return jsonify({
        "message": "Kelas berhasil ditambahkan",
        "kelas": _kelas_payload(kelas),
    }), 201


@admin_kelas_bp.route("/kelas/<int:id_kelas>/arsip", methods=["PUT"])
@jwt_required()
def arsipkan_kelas(id_kelas):
    if not _is_admin():
        return jsonify({"message": "Hanya admin"}), 403

    kelas = Kelas.query.get_or_404(id_kelas)
    kelas.status = "selesai"
    Jadwal.query.filter_by(id_kelas=id_kelas).update({"status": "selesai"})
    db.session.commit()

    return jsonify({"message": "Kelas dan jadwal berhasil masuk arsip"}), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>/aktifkan", methods=["PUT"])
@jwt_required()
def aktifkan_kelas(id_kelas):
    if not _is_admin():
        return jsonify({"message": "Hanya admin"}), 403

    kelas = Kelas.query.get_or_404(id_kelas)
    kelas.status = "aktif"
    Jadwal.query.filter_by(id_kelas=id_kelas).update({"status": "aktif"})
    db.session.commit()

    return jsonify({"message": "Kelas dan jadwal berhasil diaktifkan"}), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>/guru", methods=["POST"])
@jwt_required()
def tambah_guru_kelas(id_kelas):
    data = request.json

    if not data or "id_guru" not in data:
        return jsonify({"message": "id_guru wajib"}), 400

    from app.models.guru import Guru

    kelas = Kelas.query.get_or_404(id_kelas)
    if not _is_status_aktif(_status_value(kelas)):
        return jsonify({"message": "Kelas sudah arsip dan tidak dapat ditambah guru"}), 400

    guru = Guru.query.get_or_404(data["id_guru"])

    if guru in kelas.guru:
        return jsonify({"message": "Guru sudah ada"}), 400

    kelas.guru.append(guru)
    db.session.commit()

    return jsonify({"message": "Guru ditambahkan"}), 201


@admin_kelas_bp.route("/kelas/<int:id_kelas>/guru", methods=["GET"])
@jwt_required()
def list_guru_kelas(id_kelas):
    kelas = Kelas.query.get_or_404(id_kelas)
    if not _is_status_aktif(_status_value(kelas)):
        return jsonify([]), 200

    return jsonify([{
        "id_guru": g.id_guru,
        "nama_guru": g.nama_guru,
        "nip": getattr(g, "nip", None),
        "status_kelas": _status_value(kelas),
    } for g in kelas.guru.all()])


@admin_kelas_bp.route("/kelas/<int:id_kelas>/murid", methods=["POST"])
@jwt_required()
def tambah_murid_kelas(id_kelas):
    data = request.json

    if not data or "id_murid" not in data:
        return jsonify({"message": "id_murid wajib"}), 400

    from app.models.murid import Murid

    kelas = Kelas.query.get_or_404(id_kelas)
    if not _is_status_aktif(_status_value(kelas)):
        return jsonify({"message": "Kelas sudah arsip dan tidak dapat ditambah murid"}), 400

    murid = Murid.query.get_or_404(data["id_murid"])

    if murid.id_kelas == id_kelas:
        return jsonify({"message": "Murid sudah di kelas ini"}), 400

    mt = MuridTingkat.query.filter_by(
        id_murid=murid.id_murid,
        status="aktif"
    ).first()

    if mt and mt.tahun_ajaran and kelas.tahun_ajaran and mt.tahun_ajaran != kelas.tahun_ajaran:
        return jsonify({
            "message": "Kelas tujuan berbeda tahun ajaran. Gunakan menu Kenaikan Kelas agar riwayat murid tetap aman."
        }), 400

    if mt and mt.id_tingkat != kelas.id_tingkat:
        return jsonify({"message": "Tingkat tidak sesuai"}), 400

    murid.id_kelas = id_kelas

    if mt:
        mt.id_kelas = id_kelas
        mt.id_tingkat = kelas.id_tingkat
        mt.tahun_ajaran = mt.tahun_ajaran or kelas.tahun_ajaran
    else:
        mt = MuridTingkat(
            id_murid=murid.id_murid,
            id_tingkat=kelas.id_tingkat,
            id_kelas=id_kelas,
            tahun_ajaran=kelas.tahun_ajaran,
            status="aktif",
        )
        db.session.add(mt)

    daftar_id_mapel = db.session.execute(
        select(kelas_mapel.c.id_mapel).where(kelas_mapel.c.id_kelas == id_kelas)
    ).scalars().all()

    murid.mapel.clear()
    for id_mapel in daftar_id_mapel:
        mapel = MataPelajaran.query.get(id_mapel)
        if mapel:
            murid.mapel.append(mapel)

    sinkron_jadwal_murid(
        id_murid=murid.id_murid,
        id_kelas=id_kelas,
        daftar_id_mapel=daftar_id_mapel,
    )

    db.session.commit()
    return jsonify({"message": "Murid ditambahkan ke kelas aktif"}), 201


@admin_kelas_bp.route("/kelas/<int:id_kelas>/murid", methods=["GET"])
@jwt_required()
def list_murid_kelas(id_kelas):
    kelas = Kelas.query.get_or_404(id_kelas)
    return jsonify(_murid_aktif_kelas_payload(kelas)), 200


@admin_kelas_bp.route("/tingkat/<int:id_tingkat>/kelas", methods=["GET"])
@jwt_required()
def get_kelas_by_tingkat(id_tingkat):
    status = (request.args.get("status") or "aktif").lower().strip()
    query = Kelas.query.filter_by(id_tingkat=id_tingkat)

    if status != "all":
        query = query.filter(Kelas.status == status)

    kelas_list = query.order_by(Kelas.nama_kelas.asc()).all()
    return jsonify([_kelas_payload(k) for k in kelas_list]), 200


@admin_kelas_bp.route("/guru/<int:id_guru>/kelas", methods=["GET"])
@jwt_required()
def get_kelas_by_guru(id_guru):
    from app.models.guru import Guru
    guru = Guru.query.get_or_404(id_guru)

    result = []
    for k in guru.kelas:
        if _status_value(k) == "aktif":
            result.append(_kelas_payload(k))

    return jsonify(result), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>", methods=["GET"])
@jwt_required()
def get_kelas(id_kelas):
    k = Kelas.query.get_or_404(id_kelas)
    return jsonify(_kelas_payload(k, include_detail=True)), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>", methods=["PUT"])
@jwt_required()
def update_kelas(id_kelas):
    data = request.json
    if not data:
        return jsonify({"message": "Data kosong"}), 400

    kelas = Kelas.query.get_or_404(id_kelas)

    if "id_tingkat" in data:
        tingkat = Tingkat.query.get(data["id_tingkat"])
        if not tingkat:
            return jsonify({"message": "Tingkat tidak valid"}), 400

    if "status" in data and data["status"] not in ["aktif", "selesai", "arsip", "nonaktif"]:
        return jsonify({"message": "Status kelas tidak valid"}), 400

    kelas.nama_kelas = data.get("nama_kelas", kelas.nama_kelas)
    kelas.tahun_ajaran = data.get("tahun_ajaran", kelas.tahun_ajaran)
    kelas.id_tingkat = data.get("id_tingkat", kelas.id_tingkat)

    if "status" in data:
        status_baru = data["status"]
        kelas.status = status_baru
        Jadwal.query.filter_by(id_kelas=id_kelas).update({"status": status_baru})

    db.session.commit()
    return jsonify({"message": "Kelas berhasil diperbarui"}), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>", methods=["DELETE"])
@jwt_required()
def hapus_kelas(id_kelas):
    kelas = Kelas.query.get_or_404(id_kelas)
    kelas.status = "selesai"
    Jadwal.query.filter_by(id_kelas=id_kelas).update({"status": "selesai"})
    db.session.commit()
    return jsonify({"message": "Kelas dipindahkan ke arsip"}), 200


@admin_kelas_bp.route("/guru/kelas", methods=["GET"])
@jwt_required()
def get_kelas_guru_login():
    claims = get_jwt()
    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    from app.models.guru import Guru
    guru = Guru.query.get_or_404(id_guru)

    result = []
    for k in guru.kelas:
        if _status_value(k) == "aktif":
            result.append(_kelas_payload(k))

    return jsonify(result), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>/murid/<int:id_murid>", methods=["DELETE"])
@jwt_required()
def hapus_murid_dari_kelas(id_kelas, id_murid):
    from app.models.murid import Murid
    murid = Murid.query.get_or_404(id_murid)
    if murid.id_kelas != id_kelas:
        return jsonify({"message": "Murid tidak di kelas ini"}), 400

    mt = MuridTingkat.query.filter_by(
        id_murid=murid.id_murid,
        id_kelas=id_kelas,
        status="aktif"
    ).first()

    if mt:
        mt.id_kelas = None

    murid.id_kelas = None
    murid.mapel.clear()
    sinkron_jadwal_murid(id_murid=murid.id_murid, id_kelas=None, daftar_id_mapel=[])
    db.session.commit()
    return jsonify({"message": "Murid dihapus dari kelas aktif"}), 200


@admin_kelas_bp.route("/kelas/<int:id_kelas>/guru/<int:id_guru>", methods=["DELETE"])
@jwt_required()
def hapus_guru_dari_kelas(id_kelas, id_guru):
    from app.models.guru import Guru
    kelas = Kelas.query.get_or_404(id_kelas)
    guru = Guru.query.get_or_404(id_guru)
    if guru not in kelas.guru:
        return jsonify({"message": "Guru tidak ada di kelas ini"}), 400
    kelas.guru.remove(guru)
    db.session.commit()
    return jsonify({"message": "Guru dihapus dari kelas"}), 200


# Blueprint umum lama yang masih mungkin dipakai file lain.
kelas_bp = Blueprint("kelas", __name__)


@kelas_bp.route("/kelas", methods=["GET"])
@jwt_required()
def list_kelas_umum():
    data = db.session.query(Kelas).filter(Kelas.status == "aktif").order_by(Kelas.nama_kelas.asc()).all()
    result = [{"id_kelas": k.id_kelas, "nama_kelas": k.nama_kelas, "status": _status_value(k)} for k in data]
    return jsonify(result), 200
