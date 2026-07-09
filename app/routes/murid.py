# app/routes/murid.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.models.murid import Murid
from app.models.kelas import Kelas
from app.models.jadwal import Jadwal
from app.models.mata_pelajaran import MataPelajaran
from app.models.murid_tingkat import MuridTingkat

murid_bp = Blueprint("murid", __name__)


def _safe_claim_int(value):
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


@murid_bp.route("/murid/mapel", methods=["GET"])
@jwt_required()
def get_mapel_murid():
    claims = get_jwt()
    role = claims.get("role")

    if role not in ["murid", "orang_tua", "admin", "guru"]:
        return jsonify({"message": "Akses ditolak"}), 403

    # Murid/orang tua hanya membaca murid yang ada di token.
    # Admin/guru boleh memakai query id_murid untuk kebutuhan rekap/detail.
    token_id_murid = _safe_claim_int(claims.get("id_murid"))
    query_id_murid = request.args.get("id_murid", type=int)

    if role in ["murid", "orang_tua"]:
        id_murid = token_id_murid or query_id_murid
    else:
        id_murid = query_id_murid or token_id_murid

    if not id_murid:
        return jsonify({"message": "id_murid wajib"}), 400

    status = (request.args.get("status") or "aktif").strip().lower()

    murid = Murid.query.get(id_murid)
    if not murid:
        return jsonify({"message": "Murid tidak ditemukan"}), 404

    mt = MuridTingkat.query.filter_by(id_murid=id_murid, status="aktif").first()

    # Untuk halaman aktif, kelas diambil dari riwayat aktif agar data lama tidak ikut muncul setelah promosi.
    id_kelas = mt.id_kelas if mt else getattr(murid, "id_kelas", None)
    if not id_kelas or (status != "all" and not mt):
        return jsonify([]), 200

    rows_query = (
        Jadwal.query
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .join(MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel)
        .filter(Jadwal.id_kelas == id_kelas)
    )

    if status != "all":
        rows_query = rows_query.filter(
            Jadwal.status == "aktif",
            Kelas.status == "aktif",
        )

    rows = rows_query.order_by(Jadwal.hari.asc(), Jadwal.jam_mulai.asc()).all()

    result = []
    for j in rows:
        kelas = getattr(j, "kelas", None)
        mapel = getattr(j, "mapel", None)
        tingkat = getattr(kelas, "tingkat", None) if kelas else None
        try:
            guru_list = [jg.guru for jg in j.jadwal_guru] if j.jadwal_guru else []
        except Exception:
            guru_list = []
        nama_guru = ", ".join([g.nama_guru for g in guru_list if g]) if guru_list else "-"

        result.append({
            "id_jadwal": j.id_jadwal,
            "id_kelas": j.id_kelas,
            "nama_kelas": kelas.nama_kelas if kelas else None,
            "kelas": kelas.nama_kelas if kelas else None,
            "status_kelas": getattr(kelas, "status", None) if kelas else None,
            "id_tingkat": getattr(kelas, "id_tingkat", None) if kelas else None,
            "tingkat": getattr(tingkat, "pangkat", None) if tingkat else None,
            "pangkat": getattr(tingkat, "pangkat", None) if tingkat else None,
            "tahun_ajaran": getattr(kelas, "tahun_ajaran", None) if kelas else None,
            "id_mapel": j.id_mapel,
            "nama_mapel": mapel.nama_mapel if mapel else None,
            "mapel": mapel.nama_mapel if mapel else None,
            "hari": j.hari,
            "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
            "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
            "status": getattr(j, "status", None),
            "status_jadwal": getattr(j, "status", None),
            "guru": nama_guru,
            "nama_guru": nama_guru,
        })

    return jsonify(result), 200
