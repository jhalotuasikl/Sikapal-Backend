from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from sqlalchemy import func
from app.extensions import db
from app.models.kuisoner import Kuisoner
from app.models.pertanyaan_kuisoner import PertanyaanKuisoner
from app.models.jawaban_kuisoner import JawabanKuisoner
from app.models.detail_jawaban_kuisoner import DetailJawabanKuisoner
from app.models.guru import Guru
from app.models.jadwal import Jadwal
from app.models.murid import Murid
from app.models.kelas import Kelas
from app.models.tingkat import Tingkat
from app.models.mata_pelajaran import MataPelajaran

# sesuaikan import ini dengan model association/relasi kamu
from app.models.jadwal_guru import JadwalGuru
from app.models.jadwal_murid import jadwal_murid

from datetime import datetime

kuisoner_bp = Blueprint("kuisoner", __name__)

SKOR_MAP = {
    "A": 100,
    "B": 75,
    "C": 50,
    "D": 25
}


def hitung_status(nilai):
    if nilai >= 86:
        return "Sangat Baik"
    elif nilai >= 71:
        return "Baik"
    elif nilai >= 56:
        return "Kurang Baik"
    else:
        return "Tidak Baik"


def murid_terdaftar_di_jadwal(id_jadwal, id_murid):
    cek = db.session.execute(
        db.select(jadwal_murid).where(
            jadwal_murid.c.id_jadwal == id_jadwal,
            jadwal_murid.c.id_murid == id_murid
        )
    ).first()
    return cek is not None


def jumlah_murid_di_jadwal(id_jadwal):
    result = db.session.execute(
        db.select(func.count()).select_from(jadwal_murid).where(
            jadwal_murid.c.id_jadwal == id_jadwal
        )
    ).scalar()
    return result or 0


def guru_mengampu_jadwal(id_guru, id_jadwal):
    cek = JadwalGuru.query.filter_by(id_guru=id_guru, id_jadwal=id_jadwal).first()
    return cek is not None


def get_tingkat_info(kelas):
    if not kelas:
        return None, None

    id_tingkat = getattr(kelas, "id_tingkat", None)
    tingkat = getattr(kelas, "tingkat", None)

    if tingkat is None and id_tingkat:
        tingkat = Tingkat.query.get(id_tingkat)

    pangkat = None
    if tingkat is not None:
        pangkat = (
            getattr(tingkat, "pangkat", None)
            or getattr(tingkat, "nama_tingkat", None)
            or getattr(tingkat, "tingkat", None)
        )

    tingkat_text = str(pangkat) if pangkat is not None else (str(id_tingkat) if id_tingkat is not None else "-")
    return id_tingkat, tingkat_text


def ringkasan_kuisoner_payload(kuisoner, jadwal, kelas, mapel, nama_guru="-", daftar_id_guru=None, daftar_guru=None):
    daftar_id_guru = daftar_id_guru or []
    daftar_guru = daftar_guru or []

    id_tingkat, tingkat_text = get_tingkat_info(kelas)
    total_murid = jumlah_murid_di_jadwal(jadwal.id_jadwal)

    total_pengisi = JawabanKuisoner.query.filter_by(
        id_kuisoner=kuisoner.id_kuisoner
    ).count()

    avg_skor = db.session.query(
        func.avg(DetailJawabanKuisoner.skor)
    ).join(
        JawabanKuisoner,
        JawabanKuisoner.id_jawaban == DetailJawabanKuisoner.id_jawaban
    ).filter(
        JawabanKuisoner.id_kuisoner == kuisoner.id_kuisoner
    ).scalar()

    avg_skor = float(avg_skor) if avg_skor is not None else 0.0
    partisipasi = (total_pengisi / total_murid * 100) if total_murid > 0 else 0

    return {
        "id_kuisoner": kuisoner.id_kuisoner,
        "id_jadwal": jadwal.id_jadwal,
        "id_tingkat": id_tingkat,
        "tingkat": tingkat_text,
        "pangkat": tingkat_text,
        "kelas": getattr(kelas, "nama_kelas", None),
        "mapel": getattr(mapel, "nama_mapel", None),
        "semester": kuisoner.semester,
        "tahun_ajaran": kuisoner.tahun_ajaran,
        "status_kuisoner": kuisoner.status,
        "jumlah_murid": total_murid,
        "jumlah_pengisi": total_pengisi,
        "partisipasi_persen": round(partisipasi, 2),
        "poin_akhir": round(avg_skor, 2),
        "status_hasil": hitung_status(avg_skor) if total_pengisi > 0 else "-",
        "id_guru_list": daftar_id_guru,
        "guru_list": daftar_guru,
        "nama_guru": nama_guru,
    }


# ================= FILTER JADWAL/KELAS UNTUK KUISONER =================
def _nilai_kosong(value):
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in ["", "null", "none", "-"]


def _ambil_attr(obj, daftar_nama, default=None):
    if obj is None:
        return default

    for nama in daftar_nama:
        if hasattr(obj, nama):
            value = getattr(obj, nama)
            if not _nilai_kosong(value):
                return value

    return default


def _to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0

    text = str(value).strip().lower()
    if text in ["1", "true", "ya", "yes", "y", "aktif", "active"]:
        return True
    if text in ["0", "false", "tidak", "no", "n", "nonaktif", "non-aktif", "inactive"]:
        return False
    return None


def _obj_sudah_selesai_atau_riwayat(obj):
    """
    Dipakai agar dropdown admin kuisoner tidak menampilkan jadwal/kelas
    yang sudah selesai, riwayat, arsip, atau nonaktif.

    Dibuat fleksibel karena nama kolom di model bisa berbeda-beda.
    """
    if obj is None:
        return False

    status_values_blokir = {
        "selesai",
        "riwayat",
        "arsip",
        "diarsipkan",
        "nonaktif",
        "non-aktif",
        "inactive",
        "tamat",
        "lulus",
        "alumni",
        "hapus",
        "dihapus",
    }

    # Kolom status berbentuk teks.
    status = _ambil_attr(obj, [
        "status",
        "status_kelas",
        "kelas_status",
        "status_riwayat",
        "status_murid_kelas",
        "status_jadwal",
        "jadwal_status",
        "keterangan_status",
    ])

    if status is not None:
        status_text = str(status).strip().lower()
        if status_text in status_values_blokir:
            return True

    # Kolom boolean yang menandakan data sudah menjadi riwayat/selesai.
    for nama in [
        "is_riwayat",
        "riwayat",
        "sudah_riwayat",
        "is_selesai",
        "selesai",
        "sudah_selesai",
        "is_arsip",
        "arsip",
        "is_deleted",
        "deleted",
    ]:
        value = _ambil_attr(obj, [nama])
        if _to_bool(value) is True:
            return True

    # Kolom boolean aktif. Jika aktif = false/0, jangan tampilkan.
    for nama in [
        "is_aktif",
        "aktif",
        "status_aktif",
    ]:
        value = _ambil_attr(obj, [nama])
        if _to_bool(value) is False:
            return True

    # Kolom tanggal penanda selesai/riwayat.
    for nama in [
        "tanggal_selesai",
        "tgl_selesai",
        "waktu_selesai",
        "tanggal_riwayat",
        "tgl_riwayat",
        "tanggal_arsip",
        "archived_at",
        "deleted_at",
    ]:
        value = _ambil_attr(obj, [nama])
        if not _nilai_kosong(value):
            return True

    return False


def jadwal_bisa_dibuat_kuisoner(jadwal, kelas):
    if _obj_sudah_selesai_atau_riwayat(jadwal):
        return False
    if _obj_sudah_selesai_atau_riwayat(kelas):
        return False
    return True


def _status_obj_label(obj):
    return _ambil_attr(obj, [
        "status",
        "status_kelas",
        "kelas_status",
        "status_riwayat",
        "status_murid_kelas",
        "status_jadwal",
        "jadwal_status",
    ], default="aktif")

#ADMIN
@kuisoner_bp.route("/kuisoner", methods=["POST"])
@jwt_required()
def create_kuisoner():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat membuat kuisoner"}), 403

    data = request.get_json()

    id_jadwal = data.get("id_jadwal")
    semester = data.get("semester")
    tahun_ajaran = data.get("tahun_ajaran")
    status = data.get("status", "belum_dibuka")

    if not id_jadwal or not semester or not tahun_ajaran:
        return jsonify({"message": "id_jadwal, semester, dan tahun_ajaran wajib diisi"}), 400

    jadwal = Jadwal.query.get(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404

    kelas = Kelas.query.get(jadwal.id_kelas)
    if not jadwal_bisa_dibuat_kuisoner(jadwal, kelas):
        return jsonify({
            "message": "Kuisoner tidak bisa dibuat untuk kelas/jadwal yang sudah selesai atau riwayat"
        }), 400

    existing = Kuisoner.query.filter_by(
        id_jadwal=id_jadwal,
        semester=semester,
        tahun_ajaran=tahun_ajaran
    ).first()

    if existing:
        return jsonify({"message": "Kuisoner untuk jadwal ini pada semester tersebut sudah ada"}), 409

    kuisoner = Kuisoner(
        id_jadwal=id_jadwal,
        semester=semester,
        tahun_ajaran=tahun_ajaran,
        status=status,
        tanggal_dibuka=datetime.utcnow() if status == "dibuka" else None
    )

    db.session.add(kuisoner)
    db.session.commit()

    return jsonify({
        "message": "Kuisoner berhasil dibuat",
        "data": {
            "id_kuisoner": kuisoner.id_kuisoner,
            "id_jadwal": kuisoner.id_jadwal,
            "semester": kuisoner.semester,
            "tahun_ajaran": kuisoner.tahun_ajaran,
            "status": kuisoner.status
        }
    }), 201

@kuisoner_bp.route("/kuisoner/<int:id_kuisoner>/status", methods=["PUT"])
@jwt_required()
def update_status_kuisoner(id_kuisoner):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat mengubah status kuisoner"}), 403

    data = request.get_json()
    status = data.get("status")

    if status not in ["belum_dibuka", "dibuka", "ditutup", "selesai"]:
        return jsonify({"message": "Status tidak valid"}), 400

    kuisoner = Kuisoner.query.get(id_kuisoner)
    if not kuisoner:
        return jsonify({"message": "Kuisoner tidak ditemukan"}), 404

    kuisoner.status = status

    if status == "dibuka" and not kuisoner.tanggal_dibuka:
        kuisoner.tanggal_dibuka = datetime.utcnow()

    if status in ["ditutup", "selesai"]:
        kuisoner.tanggal_ditutup = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "message": "Status kuisoner berhasil diperbarui",
        "data": {
            "id_kuisoner": kuisoner.id_kuisoner,
            "status": kuisoner.status
        }
    }), 200


@kuisoner_bp.route("/kuisoner/<int:id_kuisoner>", methods=["DELETE"])
@jwt_required()
def delete_kuisoner(id_kuisoner):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat menghapus kuisoner"}), 403

    kuisoner = Kuisoner.query.get(id_kuisoner)
    if not kuisoner:
        return jsonify({"message": "Kuisoner tidak ditemukan"}), 404

    try:
        jawaban_rows = JawabanKuisoner.query.filter_by(id_kuisoner=id_kuisoner).all()
        for jawaban in jawaban_rows:
            DetailJawabanKuisoner.query.filter_by(id_jawaban=jawaban.id_jawaban).delete(synchronize_session=False)

        JawabanKuisoner.query.filter_by(id_kuisoner=id_kuisoner).delete(synchronize_session=False)
        db.session.delete(kuisoner)
        db.session.commit()

        return jsonify({"message": "Kuisoner berhasil dihapus"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": "Gagal menghapus kuisoner",
            "error": str(e)
        }), 500

#murid
@kuisoner_bp.route("/murid/kuisoner", methods=["GET"])
@jwt_required()
def get_kuisoner_tersedia_murid():
    claims = get_jwt()
    if claims.get("role") != "murid":
        return jsonify({"message": "Hanya murid"}), 403

    id_murid = claims.get("id_murid")
    if not id_murid:
        return jsonify({"message": "id_murid tidak ditemukan di token"}), 400

    rows = db.session.query(
        Kuisoner,
        Jadwal,
        Kelas,
        MataPelajaran
    ).join(
        Jadwal, Jadwal.id_jadwal == Kuisoner.id_jadwal
    ).join(
        Kelas, Kelas.id_kelas == Jadwal.id_kelas
    ).join(
        MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel
    ).join(
        jadwal_murid, jadwal_murid.c.id_jadwal == Jadwal.id_jadwal
    ).filter(
        jadwal_murid.c.id_murid == id_murid,
        Kuisoner.status == "dibuka",
        Jadwal.status == "aktif",
        Kelas.status == "aktif",
    ).all()

    hasil = []
    for kuisoner, jadwal, kelas, mapel in rows:
        sudah_isi = JawabanKuisoner.query.filter_by(
            id_kuisoner=kuisoner.id_kuisoner,
            id_murid=id_murid
        ).first()

        id_tingkat, tingkat_text = get_tingkat_info(kelas)

        hasil.append({
            "id_kuisoner": kuisoner.id_kuisoner,
            "id_jadwal": kuisoner.id_jadwal,
            "semester": kuisoner.semester,
            "tahun_ajaran": kuisoner.tahun_ajaran,
            "status": kuisoner.status,
            "id_tingkat": id_tingkat,
            "tingkat": tingkat_text,
            "pangkat": tingkat_text,
            "kelas": getattr(kelas, "nama_kelas", None),
            "mapel": getattr(mapel, "nama_mapel", None),
            "hari": getattr(jadwal, "hari", None),
            "sudah_isi": sudah_isi is not None
        })

    return jsonify(hasil), 200

@kuisoner_bp.route("/murid/kuisoner/<int:id_kuisoner>", methods=["GET"])
@jwt_required()
def detail_kuisoner_murid(id_kuisoner):
    claims = get_jwt()
    if claims.get("role") != "murid":
        return jsonify({"message": "Hanya murid"}), 403

    id_murid = claims.get("id_murid")
    kuisoner = Kuisoner.query.get(id_kuisoner)

    if not kuisoner:
        return jsonify({"message": "Kuisoner tidak ditemukan"}), 404

    if kuisoner.status != "dibuka":
        return jsonify({"message": "Kuisoner belum dibuka atau sudah ditutup"}), 400

    if not murid_terdaftar_di_jadwal(kuisoner.id_jadwal, id_murid):
        return jsonify({"message": "Murid tidak terdaftar pada jadwal ini"}), 403

    sudah_isi = JawabanKuisoner.query.filter_by(
        id_kuisoner=id_kuisoner,
        id_murid=id_murid
    ).first()

    pertanyaan = PertanyaanKuisoner.query.filter_by(aktif=True).all()

    return jsonify({
        "id_kuisoner": kuisoner.id_kuisoner,
        "id_jadwal": kuisoner.id_jadwal,
        "semester": kuisoner.semester,
        "tahun_ajaran": kuisoner.tahun_ajaran,
        "sudah_isi": sudah_isi is not None,
        "pertanyaan": [
            {
                "id_pertanyaan": p.id_pertanyaan,
                "pertanyaan": p.pertanyaan
            } for p in pertanyaan
        ],
        "opsi": [
            {"kode": "A", "label": "Sangat Baik", "skor": 100},
            {"kode": "B", "label": "Baik", "skor": 75},
            {"kode": "C", "label": "Kurang Baik", "skor": 50},
            {"kode": "D", "label": "Tidak Baik", "skor": 25}
        ]
    }), 200

@kuisoner_bp.route("/murid/kuisoner/<int:id_kuisoner>/submit", methods=["POST"])
@jwt_required()
def submit_kuisoner_murid(id_kuisoner):
    claims = get_jwt()
    if claims.get("role") != "murid":
        return jsonify({"message": "Hanya murid"}), 403

    id_murid = claims.get("id_murid")
    data = request.get_json()
    daftar_jawaban = data.get("jawaban", [])

    kuisoner = Kuisoner.query.get(id_kuisoner)
    if not kuisoner:
        return jsonify({"message": "Kuisoner tidak ditemukan"}), 404

    if kuisoner.status != "dibuka":
        return jsonify({"message": "Kuisoner tidak sedang dibuka"}), 400

    if not murid_terdaftar_di_jadwal(kuisoner.id_jadwal, id_murid):
        return jsonify({"message": "Murid tidak terdaftar pada jadwal ini"}), 403

    existing = JawabanKuisoner.query.filter_by(
        id_kuisoner=id_kuisoner,
        id_murid=id_murid
    ).first()

    if existing:
        return jsonify({"message": "Murid sudah pernah mengisi kuisoner ini"}), 409

    pertanyaan_aktif = PertanyaanKuisoner.query.filter_by(aktif=True).all()
    pertanyaan_ids = {p.id_pertanyaan for p in pertanyaan_aktif}

    if not daftar_jawaban:
        return jsonify({"message": "Jawaban tidak boleh kosong"}), 400

    if len(daftar_jawaban) != len(pertanyaan_ids):
        return jsonify({"message": "Semua pertanyaan wajib dijawab"}), 400

    id_terjawab = set()
    for item in daftar_jawaban:
        id_pertanyaan = item.get("id_pertanyaan")
        pilihan = item.get("pilihan")

        if id_pertanyaan not in pertanyaan_ids:
            return jsonify({"message": f"Pertanyaan {id_pertanyaan} tidak valid"}), 400

        if pilihan not in SKOR_MAP:
            return jsonify({"message": f"Pilihan untuk pertanyaan {id_pertanyaan} tidak valid"}), 400

        if id_pertanyaan in id_terjawab:
            return jsonify({"message": f"Pertanyaan {id_pertanyaan} diisi lebih dari sekali"}), 400

        id_terjawab.add(id_pertanyaan)

    jawaban = JawabanKuisoner(
        id_kuisoner=id_kuisoner,
        id_murid=id_murid
    )
    db.session.add(jawaban)
    db.session.flush()

    total_skor = 0

    for item in daftar_jawaban:
        id_pertanyaan = item["id_pertanyaan"]
        pilihan = item["pilihan"]
        skor = SKOR_MAP[pilihan]
        total_skor += skor

        detail = DetailJawabanKuisoner(
            id_jawaban=jawaban.id_jawaban,
            id_pertanyaan=id_pertanyaan,
            pilihan=pilihan,
            skor=skor
        )
        db.session.add(detail)

    db.session.commit()

    rata_rata = total_skor / len(daftar_jawaban)

    return jsonify({
        "message": "Kuisoner berhasil dikirim",
        "data": {
            "id_jawaban": jawaban.id_jawaban,
            "total_skor": total_skor,
            "rata_rata": round(rata_rata, 2),
            "status": hitung_status(rata_rata)
        }
    }), 201

#guru
@kuisoner_bp.route("/guru/kuisoner", methods=["GET"])
@jwt_required()
def get_hasil_kuisoner_guru():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Hanya guru"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ditemukan di token"}), 400

    rows = db.session.query(
        Kuisoner,
        Jadwal,
        Kelas,
        MataPelajaran
    ).join(
        Jadwal, Jadwal.id_jadwal == Kuisoner.id_jadwal
    ).join(
        JadwalGuru, JadwalGuru.id_jadwal == Jadwal.id_jadwal
    ).join(
        Kelas, Kelas.id_kelas == Jadwal.id_kelas
    ).join(
        MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel
    ).filter(
        JadwalGuru.id_guru == id_guru,
        Jadwal.status == "aktif",
        Kelas.status == "aktif",
    ).all()

    hasil = []

    for kuisoner, jadwal, kelas, mapel in rows:
        hasil.append(
            ringkasan_kuisoner_payload(
                kuisoner,
                jadwal,
                kelas,
                mapel,
            )
        )

    return jsonify(hasil), 200

@kuisoner_bp.route("/guru/kuisoner/<int:id_kuisoner>", methods=["GET"])
@jwt_required()
def detail_hasil_kuisoner_guru(id_kuisoner):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Hanya guru"}), 403

    id_guru = claims.get("id_guru")
    kuisoner = Kuisoner.query.get(id_kuisoner)

    if not kuisoner:
        return jsonify({"message": "Kuisoner tidak ditemukan"}), 404

    if not guru_mengampu_jadwal(id_guru, kuisoner.id_jadwal):
        return jsonify({"message": "Guru tidak berhak melihat kuisoner ini"}), 403

    jadwal = Jadwal.query.get(kuisoner.id_jadwal)
    kelas = Kelas.query.get(jadwal.id_kelas) if jadwal else None
    mapel = MataPelajaran.query.get(jadwal.id_mapel) if jadwal else None

    total_murid = jumlah_murid_di_jadwal(kuisoner.id_jadwal)
    total_pengisi = JawabanKuisoner.query.filter_by(id_kuisoner=id_kuisoner).count()

    avg_total = db.session.query(
        func.avg(DetailJawabanKuisoner.skor)
    ).join(
        JawabanKuisoner, JawabanKuisoner.id_jawaban == DetailJawabanKuisoner.id_jawaban
    ).filter(
        JawabanKuisoner.id_kuisoner == id_kuisoner
    ).scalar()

    avg_total = float(avg_total) if avg_total is not None else 0.0
    partisipasi = (total_pengisi / total_murid * 100) if total_murid > 0 else 0

    detail_per_pertanyaan = db.session.query(
        PertanyaanKuisoner.id_pertanyaan,
        PertanyaanKuisoner.pertanyaan,
        func.avg(DetailJawabanKuisoner.skor).label("rata_rata")
    ).join(
        DetailJawabanKuisoner,
        DetailJawabanKuisoner.id_pertanyaan == PertanyaanKuisoner.id_pertanyaan
    ).join(
        JawabanKuisoner,
        JawabanKuisoner.id_jawaban == DetailJawabanKuisoner.id_jawaban
    ).filter(
        JawabanKuisoner.id_kuisoner == id_kuisoner
    ).group_by(
        PertanyaanKuisoner.id_pertanyaan,
        PertanyaanKuisoner.pertanyaan
    ).all()

    id_tingkat, tingkat_text = get_tingkat_info(kelas)

    return jsonify({
        "id_kuisoner": kuisoner.id_kuisoner,
        "id_jadwal": kuisoner.id_jadwal,
        "id_tingkat": id_tingkat,
        "tingkat": tingkat_text,
        "pangkat": tingkat_text,
        "kelas": getattr(kelas, "nama_kelas", None),
        "mapel": getattr(mapel, "nama_mapel", None),
        "semester": kuisoner.semester,
        "tahun_ajaran": kuisoner.tahun_ajaran,
        "jumlah_murid": total_murid,
        "jumlah_pengisi": total_pengisi,
        "partisipasi_persen": round(partisipasi, 2),
        "poin_akhir": round(avg_total, 2),
        "status_hasil": hitung_status(avg_total) if total_pengisi > 0 else "-",
        "detail_pertanyaan": [
            {
                "id_pertanyaan": row.id_pertanyaan,
                "pertanyaan": row.pertanyaan,
                "rata_rata": round(float(row.rata_rata or 0), 2),
                "status": hitung_status(float(row.rata_rata or 0))
            }
            for row in detail_per_pertanyaan
        ]
    }), 200

#ADMINLIAT
@kuisoner_bp.route("/admin/kuisoner/hasil", methods=["GET"])
@jwt_required()
def get_semua_hasil_kuisoner_admin():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    rows = db.session.query(
        Kuisoner,
        Jadwal,
        Kelas,
        MataPelajaran
    ).join(
        Jadwal, Jadwal.id_jadwal == Kuisoner.id_jadwal
    ).join(
        Kelas, Kelas.id_kelas == Jadwal.id_kelas
    ).join(
        MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel
    ).all()

    hasil = []

    for kuisoner, jadwal, kelas, mapel in rows:
        total_murid = jumlah_murid_di_jadwal(jadwal.id_jadwal)

        total_pengisi = JawabanKuisoner.query.filter_by(
            id_kuisoner=kuisoner.id_kuisoner
        ).count()

        avg_skor = db.session.query(
            func.avg(DetailJawabanKuisoner.skor)
        ).join(
            JawabanKuisoner,
            JawabanKuisoner.id_jawaban == DetailJawabanKuisoner.id_jawaban
        ).filter(
            JawabanKuisoner.id_kuisoner == kuisoner.id_kuisoner
        ).scalar()

        avg_skor = float(avg_skor) if avg_skor is not None else 0.0
        partisipasi = (total_pengisi / total_murid * 100) if total_murid > 0 else 0

        # ================= AMBIL DATA GURU =================
        guru_rows = db.session.query(
            JadwalGuru,
            Guru
        ).join(
            Guru, Guru.id_guru == JadwalGuru.id_guru
        ).filter(
            JadwalGuru.id_jadwal == jadwal.id_jadwal
        ).all()

        daftar_id_guru = []
        daftar_guru = []

        for jadwal_guru, guru in guru_rows:
            daftar_id_guru.append(guru.id_guru)
            daftar_guru.append({
                "id_guru": guru.id_guru,
                "nama_guru": getattr(guru, "nama_guru", None)
            })

        nama_guru = ", ".join([
            g["nama_guru"] for g in daftar_guru if g["nama_guru"]
        ]) if daftar_guru else "-"

        hasil.append(
            ringkasan_kuisoner_payload(
                kuisoner,
                jadwal,
                kelas,
                mapel,
                nama_guru=nama_guru,
                daftar_id_guru=daftar_id_guru,
                daftar_guru=daftar_guru,
            )
        )

    return jsonify(hasil), 200
@kuisoner_bp.route("/admin/kuisoner/jadwal", methods=["GET"])
@jwt_required()
def get_jadwal_admin_untuk_kuisoner():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"message": "Hanya admin"}), 403

    rows = db.session.query(
        Jadwal,
        Kelas,
        MataPelajaran
    ).join(
        Kelas, Kelas.id_kelas == Jadwal.id_kelas
    ).join(
        MataPelajaran, MataPelajaran.id_mapel == Jadwal.id_mapel
    ).all()

    hasil = []
    for jadwal, kelas, mapel in rows:
        # FILTER UTAMA: jangan kirim jadwal/kelas selesai/riwayat ke Flutter.
        if not jadwal_bisa_dibuat_kuisoner(jadwal, kelas):
            continue

        guru_rows = JadwalGuru.query.filter_by(id_jadwal=jadwal.id_jadwal).all()
        id_guru_list = [g.id_guru for g in guru_rows]

        id_tingkat, tingkat_text = get_tingkat_info(kelas)

        hasil.append({
            "id_jadwal": jadwal.id_jadwal,
            "id_kelas": getattr(kelas, "id_kelas", None),
            "id_mapel": getattr(mapel, "id_mapel", None),
            "id_tingkat": id_tingkat,
            "tingkat": tingkat_text,
            "pangkat": tingkat_text,
            "kelas": getattr(kelas, "nama_kelas", None),
            "nama_kelas": getattr(kelas, "nama_kelas", None),
            "mapel": getattr(mapel, "nama_mapel", None),
            "nama_mapel": getattr(mapel, "nama_mapel", None),
            "hari": getattr(jadwal, "hari", None),
            "jam_mulai": str(getattr(jadwal, "jam_mulai", "")),
            "jam_selesai": str(getattr(jadwal, "jam_selesai", "")),
            "tahun_ajaran": _ambil_attr(jadwal, ["tahun_ajaran", "tahunAjaran", "ta", "tahun"], default=None)
                or _ambil_attr(kelas, ["tahun_ajaran", "tahunAjaran", "ta", "tahun"], default=None),
            "status_jadwal": str(_status_obj_label(jadwal)),
            "status_kelas": str(_status_obj_label(kelas)),
            "id_guru_list": id_guru_list,
            "label": f'{getattr(mapel, "nama_mapel", "-")} - {getattr(kelas, "nama_kelas", "-")} - {tingkat_text}'
        })

    return jsonify(hasil), 200
