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
from app.models.periode_akademik import PeriodeAkademik
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
    """Sesuaikan mapel/jadwal murid dengan kelas aktif yang baru."""
    daftar_id_mapel = _get_daftar_id_mapel_by_kelas(kelas_baru.id_kelas)

    murid.mapel.clear()

    for id_mapel in daftar_id_mapel:
        mapel = MataPelajaran.query.get(id_mapel)
        if mapel and mapel not in murid.mapel:
            murid.mapel.append(mapel)

    sinkron_jadwal_murid(
        id_murid=murid.id_murid,
        id_kelas=kelas_baru.id_kelas,
        daftar_id_mapel=daftar_id_mapel,
    )

    jumlah_jadwal = 0
    if daftar_id_mapel:
        jumlah_jadwal = Jadwal.query.filter(
            Jadwal.id_kelas == kelas_baru.id_kelas,
            Jadwal.id_mapel.in_(daftar_id_mapel),
            Jadwal.status == "aktif",
        ).count()

    return {
        "jumlah_mapel": len(daftar_id_mapel),
        "jumlah_jadwal": jumlah_jadwal,
    }


def _nama_kelas_normal(value):
    return " ".join(str(value or "").strip().lower().split())


def _urutan_tingkat(value):
    text = str(value or "").strip().upper()
    try:
        return int(text)
    except Exception:
        pass

    roman = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
        "IX": 9,
        "X": 10,
        "XI": 11,
        "XII": 12,
    }
    return roman.get(text)


def _cari_atau_buat_kelas_tinggal(kelas_lama, tahun_ajaran_baru):
    """Gunakan kelas aktif yang sama bila ada, selain itu buat wadah baru.

    Kelas baru hanya menyalin identitas kelas: nama, tingkat, tahun ajaran,
    dan status. Mapel, guru, serta jadwal tidak disalin agar dapat disiapkan
    manual oleh admin melalui detail kelas.
    """
    kandidat = (
        Kelas.query
        .filter(
            Kelas.id_tingkat == kelas_lama.id_tingkat,
            Kelas.tahun_ajaran == tahun_ajaran_baru,
            Kelas.status == "aktif",
        )
        .order_by(Kelas.id_kelas.asc())
        .with_for_update()
        .all()
    )

    nama_dicari = _nama_kelas_normal(kelas_lama.nama_kelas)
    for kelas in kandidat:
        if _nama_kelas_normal(kelas.nama_kelas) == nama_dicari:
            return kelas, False

    kelas_baru = Kelas(
        nama_kelas=str(kelas_lama.nama_kelas or "").strip(),
        tahun_ajaran=tahun_ajaran_baru,
        id_tingkat=kelas_lama.id_tingkat,
        status="aktif",
    )
    db.session.add(kelas_baru)
    db.session.flush()
    return kelas_baru, True


def _tutup_riwayat_aktif_lain(id_murid, kecuali_id=None):
    query = MuridTingkat.query.filter(
        MuridTingkat.id_murid == id_murid,
        MuridTingkat.status == "aktif",
    )
    if kecuali_id is not None:
        query = query.filter(MuridTingkat.id != kecuali_id)

    for riwayat in query.all():
        riwayat.status = "selesai"


def _aktifkan_riwayat_baru(murid, kelas_baru, tahun_ajaran_baru):
    riwayat = (
        MuridTingkat.query
        .filter_by(
            id_murid=murid.id_murid,
            id_tingkat=kelas_baru.id_tingkat,
            id_kelas=kelas_baru.id_kelas,
            tahun_ajaran=tahun_ajaran_baru,
        )
        .order_by(MuridTingkat.id.desc())
        .first()
    )

    if riwayat:
        riwayat.status = "aktif"
    else:
        riwayat = MuridTingkat(
            id_murid=murid.id_murid,
            id_tingkat=kelas_baru.id_tingkat,
            id_kelas=kelas_baru.id_kelas,
            tahun_ajaran=tahun_ajaran_baru,
            status="aktif",
        )
        db.session.add(riwayat)

    return riwayat


def _arsipkan_kelas_lama(kelas_lama):
    """Tutup kelas dan seluruh jadwal lama tanpa menghapus data riwayat."""
    kelas_lama.status = "selesai"
    jumlah_jadwal = Jadwal.query.filter_by(id_kelas=kelas_lama.id_kelas).update(
        {"status": "selesai"},
        synchronize_session=False,
    )

    # Relasi kelas_mapel sengaja dipertahankan. MataPelajaran merupakan master
    # per tingkat dan tidak memiliki status per kelas; kelas serta jadwal yang
    # selesai sudah membuat pembelajaran lama tidak tampil pada data aktif,
    # sementara relasi mapelnya tetap tersedia pada Riwayat Kelas.
    return {
        "kelas_selesai": True,
        "jumlah_jadwal_selesai": jumlah_jadwal,
        "jumlah_mapel_riwayat": len(
            _get_daftar_id_mapel_by_kelas(kelas_lama.id_kelas)
        ),
    }


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

    raw_ids = (
        data.get("id_murid")
        or data.get("id_murid_list")
        or data.get("murid_ids")
        or []
    )
    if isinstance(raw_ids, int):
        raw_ids = [raw_ids]

    id_murid_list = []
    for item in raw_ids:
        item_int = _to_int(item)
        if item_int is not None and item_int not in id_murid_list:
            id_murid_list.append(item_int)

    id_kelas_lama = _to_int(
        data.get("id_kelas_lama")
        or data.get("id_kelas_asal")
    )
    id_kelas_baru = _to_int(
        data.get("id_kelas_baru")
        or data.get("id_kelas_tujuan")
        or data.get("id_kelas")
    )

    if not id_murid_list:
        return jsonify({"success": False, "message": "Pilih minimal satu murid yang naik kelas"}), 400

    if not id_kelas_lama:
        return jsonify({"success": False, "message": "Kelas asal wajib dipilih"}), 400

    if not id_kelas_baru:
        return jsonify({"success": False, "message": "Kelas tujuan wajib dipilih"}), 400

    if id_kelas_lama == id_kelas_baru:
        return jsonify({"success": False, "message": "Kelas tujuan harus berbeda dari kelas asal"}), 400

    periode_aktif = PeriodeAkademik.aktif()
    if not periode_aktif:
        return jsonify({
            "success": False,
            "message": "Periode akademik aktif belum diatur. Atur periode terbaru sebelum memproses kenaikan kelas."
        }), 400

    tahun_ajaran_baru = str(periode_aktif.tahun_ajaran or "").strip()
    if not tahun_ajaran_baru:
        return jsonify({"success": False, "message": "Tahun ajaran aktif tidak valid"}), 400

    try:
        kelas_lama = (
            Kelas.query
            .filter_by(id_kelas=id_kelas_lama)
            .with_for_update()
            .first()
        )
        kelas_baru = (
            Kelas.query
            .filter_by(id_kelas=id_kelas_baru)
            .with_for_update()
            .first()
        )

        if not kelas_lama:
            return jsonify({"success": False, "message": "Kelas asal tidak ditemukan"}), 404

        if not kelas_baru:
            return jsonify({"success": False, "message": "Kelas tujuan tidak ditemukan"}), 404

        if str(kelas_lama.status or "").strip().lower() != "aktif":
            return jsonify({"success": False, "message": "Kelas asal sudah selesai dan tidak dapat dipromosikan ulang"}), 400

        if str(kelas_baru.status or "").strip().lower() != "aktif":
            return jsonify({"success": False, "message": "Kelas tujuan harus berstatus aktif"}), 400

        if str(kelas_lama.tahun_ajaran or "").strip() == tahun_ajaran_baru:
            return jsonify({
                "success": False,
                "message": "Kelas asal harus berasal dari tahun ajaran sebelumnya, bukan tahun ajaran aktif saat ini."
            }), 400

        if str(kelas_baru.tahun_ajaran or "").strip() != tahun_ajaran_baru:
            return jsonify({
                "success": False,
                "message": f"Kelas tujuan harus mengikuti tahun ajaran aktif {tahun_ajaran_baru}."
            }), 400

        if kelas_lama.id_tingkat == kelas_baru.id_tingkat:
            return jsonify({
                "success": False,
                "message": "Kelas tujuan harus berada pada tingkat berikutnya, bukan tingkat yang sama."
            }), 400

        tingkat_lama = Tingkat.query.get(kelas_lama.id_tingkat)
        tingkat_baru = Tingkat.query.get(kelas_baru.id_tingkat)
        urutan_lama = _urutan_tingkat(tingkat_lama.pangkat if tingkat_lama else None)
        urutan_baru = _urutan_tingkat(tingkat_baru.pangkat if tingkat_baru else None)
        if (
            urutan_lama is not None
            and urutan_baru is not None
            and urutan_baru != urutan_lama + 1
        ):
            return jsonify({
                "success": False,
                "message": "Kelas tujuan harus tepat satu tingkat di atas kelas asal."
            }), 400

        anggota_aktif = (
            db.session.query(MuridTingkat, Murid)
            .join(Murid, Murid.id_murid == MuridTingkat.id_murid)
            .filter(
                MuridTingkat.id_kelas == kelas_lama.id_kelas,
                MuridTingkat.status == "aktif",
            )
            .order_by(Murid.nama_murid.asc())
            .with_for_update()
            .all()
        )

        if not anggota_aktif:
            return jsonify({
                "success": False,
                "message": "Kelas asal tidak memiliki murid aktif yang dapat diproses."
            }), 400

        seluruh_id = {murid.id_murid for _, murid in anggota_aktif}
        dipilih_id = set(id_murid_list)
        id_tidak_valid = sorted(dipilih_id - seluruh_id)
        if id_tidak_valid:
            return jsonify({
                "success": False,
                "message": "Sebagian murid yang dipilih bukan anggota aktif kelas asal. Muat ulang daftar murid.",
                "id_murid_tidak_valid": id_tidak_valid,
            }), 400

        jumlah_tinggal = len(seluruh_id - dipilih_id)
        kelas_tinggal = None
        kelas_tinggal_dibuat = False

        if jumlah_tinggal > 0:
            kelas_tinggal, kelas_tinggal_dibuat = _cari_atau_buat_kelas_tinggal(
                kelas_lama=kelas_lama,
                tahun_ajaran_baru=tahun_ajaran_baru,
            )

        data_naik = []
        data_tinggal = []
        peringatan = []

        for riwayat_lama, murid in anggota_aktif:
            _tutup_riwayat_aktif_lain(
                id_murid=murid.id_murid,
                kecuali_id=riwayat_lama.id,
            )

            if murid.id_murid in dipilih_id:
                riwayat_lama.status = "selesai"
                _aktifkan_riwayat_baru(
                    murid=murid,
                    kelas_baru=kelas_baru,
                    tahun_ajaran_baru=tahun_ajaran_baru,
                )
                murid.id_kelas = kelas_baru.id_kelas
                sync_info = _sync_mapel_dan_jadwal(murid, kelas_baru)

                if sync_info["jumlah_mapel"] == 0:
                    peringatan.append({
                        "id_murid": murid.id_murid,
                        "nama_murid": murid.nama_murid,
                        "message": "Kelas tujuan belum memiliki mata pelajaran. Murid tetap naik kelas, tetapi mapel dan jadwal belum tersinkron.",
                    })

                data_naik.append({
                    "id_murid": murid.id_murid,
                    "nis": murid.nis,
                    "nama_murid": murid.nama_murid,
                    "status_riwayat_lama": "selesai",
                    "id_kelas_baru": kelas_baru.id_kelas,
                    "kelas_baru": kelas_baru.nama_kelas,
                    "tahun_ajaran_baru": tahun_ajaran_baru,
                    **sync_info,
                })
                continue

            riwayat_lama.status = "tinggal_kelas"
            _aktifkan_riwayat_baru(
                murid=murid,
                kelas_baru=kelas_tinggal,
                tahun_ajaran_baru=tahun_ajaran_baru,
            )
            murid.id_kelas = kelas_tinggal.id_kelas
            sync_info = _sync_mapel_dan_jadwal(murid, kelas_tinggal)

            data_tinggal.append({
                "id_murid": murid.id_murid,
                "nis": murid.nis,
                "nama_murid": murid.nama_murid,
                "status_riwayat_lama": "tinggal_kelas",
                "status_riwayat_baru": "aktif",
                "id_kelas_baru": kelas_tinggal.id_kelas,
                "kelas_baru": kelas_tinggal.nama_kelas,
                "id_tingkat": kelas_tinggal.id_tingkat,
                "tahun_ajaran_baru": tahun_ajaran_baru,
                **sync_info,
            })

        hasil_arsip = _arsipkan_kelas_lama(kelas_lama)
        db.session.commit()

        kelas_tinggal_payload = None
        if kelas_tinggal:
            kelas_tinggal_payload = {
                "id_kelas": kelas_tinggal.id_kelas,
                "nama_kelas": kelas_tinggal.nama_kelas,
                "id_tingkat": kelas_tinggal.id_tingkat,
                "tahun_ajaran": kelas_tinggal.tahun_ajaran,
                "status": kelas_tinggal.status,
                "dibuat_baru": kelas_tinggal_dibuat,
            }

        return jsonify({
            "success": True,
            "message": (
                f"Kenaikan kelas selesai: {len(data_naik)} murid naik kelas dan "
                f"{len(data_tinggal)} murid tinggal kelas."
            ),
            "berhasil": len(data_naik),
            "gagal": 0,
            "tinggal_kelas": len(data_tinggal),
            "data_berhasil": data_naik,
            "data_tinggal_kelas": data_tinggal,
            "detail_gagal": [],
            "peringatan": peringatan,
            "kelas_lama": {
                "id_kelas": kelas_lama.id_kelas,
                "nama_kelas": kelas_lama.nama_kelas,
                "tahun_ajaran": kelas_lama.tahun_ajaran,
                "status": kelas_lama.status,
            },
            "hasil_arsip_kelas_lama": hasil_arsip,
            "kelas_tinggal_kelas": kelas_tinggal_payload,
            "kelas_tinggal_dibuat": kelas_tinggal_dibuat,
            "tahun_ajaran_aktif": tahun_ajaran_baru,
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
