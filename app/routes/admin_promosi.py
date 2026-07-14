from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, verify_jwt_in_request, get_jwt
from sqlalchemy import select, func

from app import db
from app.models.murid import Murid
from app.models.kelas import Kelas
from app.models.jadwal import Jadwal
from app.models.tingkat import Tingkat
from app.models.murid_tingkat import MuridTingkat
from app.models.mata_pelajaran import MataPelajaran
from app.models.kelas_mapel import kelas_mapel
from app.utils.jadwal_helper import sinkron_jadwal_murid


admin_promosi_bp = Blueprint("admin_promosi", __name__)


@admin_promosi_bp.before_request
def _guard_admin_promosi():
    if request.method == "OPTIONS":
        return None

    verify_jwt_in_request()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Akses khusus admin"}), 403

    return None


STATUS_RIWAYAT_LAMA = {"selesai", "tinggal_kelas", "lulus", "pindah"}


def _to_int(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _get_daftar_id_mapel_by_kelas(id_kelas):
    return db.session.execute(
        select(kelas_mapel.c.id_mapel).where(kelas_mapel.c.id_kelas == id_kelas)
    ).scalars().all()


def _sync_mapel_dan_jadwal(murid, kelas_baru):
    daftar_id_mapel = _get_daftar_id_mapel_by_kelas(kelas_baru.id_kelas)

    murid.mapel.clear()

    for id_mapel in daftar_id_mapel:
        mapel = MataPelajaran.query.get(id_mapel)
        if mapel and mapel not in murid.mapel:
            murid.mapel.append(mapel)

    jumlah_jadwal = sinkron_jadwal_murid(
        id_murid=murid.id_murid,
        id_kelas=kelas_baru.id_kelas,
        daftar_id_mapel=daftar_id_mapel,
    )

    return {
        "jumlah_mapel": len(daftar_id_mapel),
        "jumlah_jadwal": jumlah_jadwal,
    }




def _arsipkan_pembelajaran_kelas_lama(id_kelas):
    """Arsipkan pembelajaran lama setelah proses promosi.

    Jadwal lama selalu diselesaikan agar mapel/jadwal periode sebelumnya tidak
    tampil lagi pada halaman aktif. Kelas hanya ikut diselesaikan ketika sudah
    tidak memiliki murid aktif/tinggal kelas atau murid yang masih terdaftar.
    Jika masih ada murid yang tidak dipromosikan,
    kelas tetap aktif sebagai kelas tinggal kelas dan siap diberi jadwal baru.
    """
    if not id_kelas:
        return {"kelas_selesai": False, "masih_ada_murid_aktif": False}

    kelas = Kelas.query.get(id_kelas)
    if not kelas:
        return {"kelas_selesai": False, "masih_ada_murid_aktif": False}

    Jadwal.query.filter_by(id_kelas=id_kelas).update(
        {"status": "selesai"},
        synchronize_session=False,
    )

    masih_aktif = MuridTingkat.query.filter(
        MuridTingkat.id_kelas == id_kelas,
        func.lower(func.trim(MuridTingkat.status)).in_(["aktif", "tinggal_kelas"]),
    ).first()

    # Murid yang tidak dipilih pada proses promosi tetap memiliki id_kelas lama.
    # Pemeriksaan langsung ini menjaga kelas tetap aktif juga pada data lama yang
    # belum memiliki riwayat MuridTingkat yang lengkap.
    masih_terdaftar_di_kelas = Murid.query.filter_by(id_kelas=id_kelas).first()

    if masih_aktif or masih_terdaftar_di_kelas:
        if hasattr(kelas, "status"):
            kelas.status = "aktif"
        return {
            "kelas_selesai": False,
            "masih_ada_murid_aktif": True,
        }

    if hasattr(kelas, "status"):
        kelas.status = "selesai"

    return {"kelas_selesai": True, "masih_ada_murid_aktif": False}

def _murid_payload(murid, mt=None):
    kelas = murid.kelas
    tingkat = None

    if mt:
        tingkat = Tingkat.query.get(mt.id_tingkat)
    elif kelas:
        tingkat = Tingkat.query.get(kelas.id_tingkat)

    return {
        "id_murid": murid.id_murid,
        "nis": murid.nis,
        "nama_murid": murid.nama_murid,
        "id_kelas": murid.id_kelas,
        "kelas": kelas.nama_kelas if kelas else "-",
        "nama_kelas": kelas.nama_kelas if kelas else "-",
        "id_tingkat": mt.id_tingkat if mt else (kelas.id_tingkat if kelas else None),
        "pangkat": tingkat.pangkat if tingkat else None,
        "tahun_ajaran": mt.tahun_ajaran if mt else (kelas.tahun_ajaran if kelas else None),
        "status": mt.status if mt else None,
    }


@admin_promosi_bp.route("/promosi/murid", methods=["GET"])
@jwt_required()
def list_murid_promosi():
    """Ambil murid aktif untuk kebutuhan promosi/kenaikan kelas.

    Query opsional:
    - id_tingkat
    - id_kelas
    - tahun_ajaran
    - status, default aktif
    """
    id_tingkat = _to_int(request.args.get("id_tingkat"))
    id_kelas = _to_int(request.args.get("id_kelas"))
    tahun_ajaran = request.args.get("tahun_ajaran")
    status = request.args.get("status") or "aktif"

    query = (
        db.session.query(Murid, MuridTingkat)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .filter(MuridTingkat.status == status)
    )

    if id_tingkat is not None:
        query = query.filter(MuridTingkat.id_tingkat == id_tingkat)

    if id_kelas is not None:
        query = query.filter(MuridTingkat.id_kelas == id_kelas)

    if tahun_ajaran:
        query = query.filter(MuridTingkat.tahun_ajaran == tahun_ajaran)

    rows = query.order_by(Murid.nama_murid.asc()).all()

    return jsonify([_murid_payload(murid, mt) for murid, mt in rows]), 200


@admin_promosi_bp.route("/promosi/riwayat", methods=["GET"])
@jwt_required()
def list_riwayat_semua_murid():
    """Ambil semua riwayat kelas/tingkat murid.

    Query opsional:
    - id_tingkat
    - id_kelas
    - tahun_ajaran
    - status
    - q : pencarian nama murid / NIS
    """
    id_tingkat = _to_int(request.args.get("id_tingkat"))
    id_kelas = _to_int(request.args.get("id_kelas"))
    tahun_ajaran = request.args.get("tahun_ajaran")
    status = request.args.get("status")
    q = request.args.get("q")

    query = (
        db.session.query(MuridTingkat, Murid, Kelas, Tingkat)
        .join(Murid, Murid.id_murid == MuridTingkat.id_murid)
        .outerjoin(Kelas, Kelas.id_kelas == MuridTingkat.id_kelas)
        .outerjoin(Tingkat, Tingkat.id_tingkat == MuridTingkat.id_tingkat)
    )

    if id_tingkat is not None:
        query = query.filter(MuridTingkat.id_tingkat == id_tingkat)

    if id_kelas is not None:
        query = query.filter(MuridTingkat.id_kelas == id_kelas)

    if tahun_ajaran:
        query = query.filter(MuridTingkat.tahun_ajaran == tahun_ajaran)

    if status:
        query = query.filter(MuridTingkat.status == status)

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Murid.nama_murid.ilike(like),
                Murid.nis.ilike(like),
            )
        )

    rows = (
        query
        .order_by(
            Murid.nama_murid.asc(),
            MuridTingkat.tahun_ajaran.desc(),
            MuridTingkat.id.desc(),
        )
        .all()
    )

    data = []
    for mt, murid, kelas, tingkat in rows:
        data.append({
            "id": mt.id,
            "id_murid": murid.id_murid,
            "nis": murid.nis,
            "nama_murid": murid.nama_murid,
            "id_tingkat": mt.id_tingkat,
            "pangkat": tingkat.pangkat if tingkat else None,
            "id_kelas": mt.id_kelas,
            "nama_kelas": kelas.nama_kelas if kelas else "-",
            "tahun_ajaran": mt.tahun_ajaran,
            "status": mt.status,
            "kelas_aktif_sekarang": murid.id_kelas,
        })

    return jsonify(data), 200


@admin_promosi_bp.route("/promosi/riwayat/<int:id_murid>", methods=["GET"])
@jwt_required()
def riwayat_murid(id_murid):
    murid = Murid.query.get_or_404(id_murid)

    riwayat = (
        MuridTingkat.query
        .filter_by(id_murid=id_murid)
        .order_by(MuridTingkat.id.asc())
        .all()
    )

    data = []
    for mt in riwayat:
        kelas = Kelas.query.get(mt.id_kelas) if mt.id_kelas else None
        tingkat = Tingkat.query.get(mt.id_tingkat) if mt.id_tingkat else None
        data.append({
            "id": mt.id,
            "id_murid": mt.id_murid,
            "nis": murid.nis,
            "nama_murid": murid.nama_murid,
            "id_tingkat": mt.id_tingkat,
            "pangkat": tingkat.pangkat if tingkat else None,
            "id_kelas": mt.id_kelas,
            "nama_kelas": kelas.nama_kelas if kelas else "-",
            "tahun_ajaran": mt.tahun_ajaran,
            "status": mt.status,
        })

    return jsonify(data), 200


@admin_promosi_bp.route("/promosi/naik-kelas", methods=["POST"])
@jwt_required()
def naik_kelas():
    data = request.json or {}

    raw_ids = data.get("id_murid") or data.get("id_murid_list") or data.get("murid_ids") or []
    if isinstance(raw_ids, int):
        raw_ids = [raw_ids]

    id_murid_list = []
    for item in raw_ids:
        item_int = _to_int(item)
        if item_int is not None:
            id_murid_list.append(item_int)

    id_kelas_baru = _to_int(data.get("id_kelas_baru") or data.get("id_kelas"))
    tahun_ajaran_baru = data.get("tahun_ajaran_baru") or data.get("tahun_ajaran")
    status_lama = data.get("status_lama") or "selesai"

    if not id_murid_list:
        return jsonify({"success": False, "message": "Pilih minimal satu murid"}), 400

    if not id_kelas_baru:
        return jsonify({"success": False, "message": "Kelas tujuan wajib dipilih"}), 400

    if status_lama not in STATUS_RIWAYAT_LAMA:
        return jsonify({
            "success": False,
            "message": "Status lama tidak valid. Gunakan selesai, tinggal_kelas, lulus, atau pindah."
        }), 400

    kelas_baru = Kelas.query.get(id_kelas_baru)
    if not kelas_baru:
        return jsonify({"success": False, "message": "Kelas tujuan tidak ditemukan"}), 404

    if not tahun_ajaran_baru:
        tahun_ajaran_baru = kelas_baru.tahun_ajaran

    berhasil = []
    gagal = []
    peringatan = []
    kelas_lama_terdampak = set()

    try:
        for id_murid in id_murid_list:
            murid = Murid.query.get(id_murid)
            if not murid:
                gagal.append({"id_murid": id_murid, "error": "Murid tidak ditemukan"})
                continue

            aktif_list = MuridTingkat.query.filter_by(
                id_murid=murid.id_murid,
                status="aktif"
            ).all()

            # Tutup semua riwayat aktif lama supaya tidak ada dua kelas aktif.
            for mt_lama in aktif_list:
                if mt_lama.id_kelas:
                    kelas_lama_terdampak.add(mt_lama.id_kelas)
                mt_lama.status = status_lama

            riwayat_tujuan = MuridTingkat.query.filter_by(
                id_murid=murid.id_murid,
                id_tingkat=kelas_baru.id_tingkat,
                id_kelas=kelas_baru.id_kelas,
                tahun_ajaran=tahun_ajaran_baru,
            ).first()

            if riwayat_tujuan:
                riwayat_tujuan.status = "aktif"
            else:
                riwayat_tujuan = MuridTingkat(
                    id_murid=murid.id_murid,
                    id_tingkat=kelas_baru.id_tingkat,
                    id_kelas=kelas_baru.id_kelas,
                    tahun_ajaran=tahun_ajaran_baru,
                    status="aktif",
                )
                db.session.add(riwayat_tujuan)

            murid.id_kelas = kelas_baru.id_kelas
            sync_info = _sync_mapel_dan_jadwal(murid, kelas_baru)

            if sync_info["jumlah_mapel"] == 0:
                peringatan.append({
                    "id_murid": murid.id_murid,
                    "nama_murid": murid.nama_murid,
                    "message": "Kelas tujuan belum memiliki mapel. Murid tetap dipromosikan, tetapi mapel/jadwal belum tersinkron."
                })

            berhasil.append({
                "id_murid": murid.id_murid,
                "nis": murid.nis,
                "nama_murid": murid.nama_murid,
                "kelas_baru": kelas_baru.nama_kelas,
                "tahun_ajaran_baru": tahun_ajaran_baru,
                **sync_info,
            })

        hasil_arsip = []
        for id_kelas_lama in kelas_lama_terdampak:
            status_arsip = _arsipkan_pembelajaran_kelas_lama(id_kelas_lama)
            hasil_arsip.append({
                "id_kelas": id_kelas_lama,
                **status_arsip,
            })

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Proses kenaikan kelas selesai",
            "berhasil": len(berhasil),
            "gagal": len(gagal),
            "data_berhasil": berhasil,
            "detail_gagal": gagal,
            "peringatan": peringatan,
            "hasil_arsip_kelas_lama": hasil_arsip,
        }), 200

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "Gagal memproses kenaikan kelas",
            "error": str(e),
        }), 500
