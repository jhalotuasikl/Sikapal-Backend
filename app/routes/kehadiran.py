# app/routes/kehadiran.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import date
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.kehadiran_murid import KehadiranMurid
from app.models.murid import Murid
from app.models.kelas import Kelas
from app.models.tingkat import Tingkat
from app.models.murid_tingkat import MuridTingkat

kehadiran_bp = Blueprint("kehadiran", __name__)


_HARI_ORDER = {
    "senin": 1,
    "selasa": 2,
    "rabu": 3,
    "kamis": 4,
    "jumat": 5,
    "jum'at": 5,
    "sabtu": 6,
    "minggu": 7,
}


def _hari_order_value(value):
    text = str(value or "").strip().lower().replace("’", "'")
    return _HARI_ORDER.get(text, 99)


def _jadwal_sort_key(jadwal):
    jam_mulai = getattr(jadwal, "jam_mulai", None)
    return (
        _hari_order_value(getattr(jadwal, "hari", None)),
        str(jam_mulai or ""),
        getattr(jadwal, "id_jadwal", 0) or 0,
    )


def _status_text(value, default="aktif"):
    return str(value or default).strip().lower()


def _normalisasi_semester_kehadiran(value, pertemuan=None):
    text = str(value or "").strip().lower()
    if text in ["2", "genap", "semester 2", "semester genap"]:
        return "genap"
    if text in ["1", "ganjil", "semester 1", "semester ganjil"]:
        return "ganjil"
    try:
        p = int(pertemuan) if pertemuan is not None else None
    except Exception:
        p = None
    return "genap" if p is not None and p >= 19 else "ganjil"


def _tahun_ajaran_jadwal(jadwal):
    kelas = getattr(jadwal, "kelas", None) or Kelas.query.get(getattr(jadwal, "id_kelas", None))
    return getattr(kelas, "tahun_ajaran", None) or ""


def _apply_absensi_semester_tahun_filter(query):
    semester = request.args.get("semester")
    tahun_ajaran = request.args.get("tahun_ajaran") or request.args.get("tahun")

    if semester and str(semester).strip().lower() not in ["all", "ganjilgenap", "1 tahun ajaran", "setahun"]:
        query = query.filter(KehadiranMurid.semester == _normalisasi_semester_kehadiran(semester))

    if tahun_ajaran:
        query = query.filter(KehadiranMurid.tahun_ajaran == tahun_ajaran)

    return query


def _pertemuan_range_from_mode(mode):
    text = str(mode or "all").strip().lower()
    if text in ["1", "ganjil", "semester 1", "semester ganjil"]:
        return 1, 18
    if text in ["2", "genap", "semester 2", "semester genap"]:
        return 19, 36
    return 1, 36


def _jadwal_kelas_aktif(jadwal):
    if not jadwal:
        return False

    if _status_text(getattr(jadwal, "status", None)) != "aktif":
        return False

    kelas = getattr(jadwal, "kelas", None) or Kelas.query.get(getattr(jadwal, "id_kelas", None))
    if kelas and _status_text(getattr(kelas, "status", None)) != "aktif":
        return False

    return True


def jadwal_milik_guru(id_jadwal: int, id_guru: int) -> bool:
    return db.session.query(JadwalGuru).filter_by(
        id_jadwal=id_jadwal,
        id_guru=id_guru
    ).first() is not None


# =====================================================
# HELPER ABSENSI GLOBAL PER MAPEL + KELAS
# =====================================================
def _jadwal_group_ids(jadwal):
    """
    Mengambil semua id_jadwal yang masih satu kelas dan satu mapel.
    Dipakai agar J1/J2/J3 tetap disimpan dengan id_jadwal masing-masing,
    tetapi pertemuan dan rekap dihitung sebagai satu mapel.
    """
    if not jadwal:
        return []

    id_jadwal = getattr(jadwal, "id_jadwal", None)
    id_kelas = getattr(jadwal, "id_kelas", None)
    id_mapel = getattr(jadwal, "id_mapel", None)

    if id_jadwal is None:
        return []

    if not _jadwal_kelas_aktif(jadwal):
        return []

    if id_kelas is None or id_mapel is None or not hasattr(Jadwal, "id_mapel"):
        return [id_jadwal]

    rows = (
        Jadwal.query
        .join(Kelas, Kelas.id_kelas == Jadwal.id_kelas)
        .filter(
            Jadwal.id_kelas == id_kelas,
            Jadwal.id_mapel == id_mapel,
            Jadwal.status == "aktif",
            Kelas.status == "aktif",
        )
        .all()
    )
    rows = sorted(rows, key=_jadwal_sort_key)

    ids = [getattr(j, "id_jadwal", None) for j in rows]
    ids = [i for i in ids if i is not None]
    return ids or [id_jadwal]


def _jadwal_group_ids_by_id(id_jadwal):
    jadwal = Jadwal.query.get(id_jadwal)
    if not jadwal:
        return None, []
    return jadwal, _jadwal_group_ids(jadwal)


def _kelas_tingkat_by_jadwal(jadwal):
    kelas_info = (
        db.session.query(Kelas, Tingkat)
        .join(Tingkat, Kelas.id_tingkat == Tingkat.id_tingkat)
        .filter(Kelas.id_kelas == jadwal.id_kelas)
        .first()
    )
    kelas_obj = kelas_info[0] if kelas_info else None
    tingkat_obj = kelas_info[1] if kelas_info else None
    return kelas_obj, tingkat_obj


def _init_rekap_item(murid, jadwal, kelas_obj=None, tingkat_obj=None):
    item = {
        "id_murid": murid.id_murid,
        "nis": getattr(murid, "nis", None),
        "nama_murid": murid.nama_murid,
        "id_tingkat": tingkat_obj.id_tingkat if tingkat_obj else None,
        "tingkat": tingkat_obj.pangkat if tingkat_obj else None,
        "pangkat": tingkat_obj.pangkat if tingkat_obj else None,
        "id_kelas": jadwal.id_kelas,
        "nama_kelas": kelas_obj.nama_kelas if kelas_obj else None,
        "id_mapel": getattr(jadwal, "id_mapel", None),
    }
    for p in range(1, 37):
        item[f"P{p}"] = ""
    return item


def _rekap_absensi_mapel(jadwal, id_jadwal_group, only_terkirim=False, semester=None, tahun_ajaran=None):
    if not _jadwal_kelas_aktif(jadwal) or not id_jadwal_group:
        return []

    kelas_obj, tingkat_obj = _kelas_tingkat_by_jadwal(jadwal)
    murid_list = (
        db.session.query(Murid)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .filter(
            MuridTingkat.id_kelas == jadwal.id_kelas,
            MuridTingkat.status == "aktif",
        )
        .order_by(Murid.nama_murid.asc())
        .all()
    )

    if not murid_list:
        murid_list = Murid.query.filter_by(id_kelas=jadwal.id_kelas).order_by(Murid.nama_murid.asc()).all()

    rows_query = (
        KehadiranMurid.query
        .filter(KehadiranMurid.id_jadwal.in_(id_jadwal_group))
    )

    if semester and str(semester).strip().lower() not in ["all", "ganjilgenap", "1 tahun ajaran", "setahun"]:
        rows_query = rows_query.filter(KehadiranMurid.semester == _normalisasi_semester_kehadiran(semester))

    if tahun_ajaran:
        rows_query = rows_query.filter(KehadiranMurid.tahun_ajaran == tahun_ajaran)

    # Halaman admin hanya boleh membaca rekap yang sudah dikirim guru.
    # Input kehadiran biasa tetap tersimpan, tetapi belum dianggap laporan admin.
    if only_terkirim:
        rows_query = rows_query.filter(KehadiranMurid.status_kirim == True)

    rows = rows_query.all()

    if not rows:
        return []

    idx = {}
    for r in rows:
        idx[(r.id_murid, r.pertemuan)] = r.status

    result = []
    for m in murid_list:
        item = _init_rekap_item(m, jadwal, kelas_obj, tingkat_obj)
        for p in range(1, 37):
            item[f"P{p}"] = idx.get((m.id_murid, p), "")
        result.append(item)

    return result


# =====================================================
# INPUT ABSENSI MURID (BERDASARKAN JADWAL)
# =====================================================
@kehadiran_bp.route("/kehadiran", methods=["POST"])
@jwt_required()
def input_kehadiran():
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    data = request.json or {}

    id_jadwal = data.get("id_jadwal")
    id_murid = data.get("id_murid")
    pertemuan = data.get("pertemuan")
    status = data.get("status") or "Alpa"
    semester = data.get("semester")
    tahun_ajaran = data.get("tahun_ajaran") or data.get("tahun")
    tanggal_in = data.get("tanggal")  # opsional: kalau mau input tanggal manual

    if not all([id_jadwal, id_murid, pertemuan]):
        return jsonify({"message": "Data tidak lengkap"}), 400

    try:
        id_jadwal = int(id_jadwal)
        id_murid = int(id_murid)
        pertemuan = int(pertemuan)
    except Exception:
        return jsonify({"message": "id_jadwal, id_murid, dan pertemuan harus angka"}), 400

    if pertemuan < 1 or pertemuan > 36:
        return jsonify({"message": "Pertemuan harus berada pada rentang 1 sampai 36"}), 400

    status_map = {
        "hadir": "Hadir",
        "izin": "Izin",
        "sakit": "Sakit",
        "alpa": "Alpa",
    }
    status = status_map.get(str(status).strip().lower())
    if not status:
        return jsonify({"message": "Status tidak valid"}), 400

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "ID guru tidak ditemukan"}), 400

    # ✅ validasi jadwal milik guru via jadwal_guru
    if not jadwal_milik_guru(int(id_jadwal), int(id_guru)):
        return jsonify({"message": "Jadwal tidak valid untuk guru ini"}), 403

    jadwal = Jadwal.query.get_or_404(id_jadwal)
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify({"message": "Jadwal/kelas sudah selesai"}), 403

    semester = _normalisasi_semester_kehadiran(semester, pertemuan)
    tahun_ajaran = tahun_ajaran or _tahun_ajaran_jadwal(jadwal)
    if not tahun_ajaran:
        return jsonify({"message": "Tahun ajaran tidak ditemukan"}), 400

    id_jadwal_group = _jadwal_group_ids(jadwal)

    # ✅ validasi murid ada di kelas jadwal
    murid = Murid.query.get_or_404(id_murid)
    if murid.id_kelas != jadwal.id_kelas:
        return jsonify({"message": "Murid bukan di kelas jadwal ini"}), 403

    # tanggal default hari ini
    tgl = date.today()
    if tanggal_in:
        try:
            y, m, d = map(int, str(tanggal_in).split("-"))
            tgl = date(y, m, d)
        except:
            return jsonify({"message": "Format tanggal harus YYYY-MM-DD"}), 400

    # update / insert
    # Pertemuan dicek secara global pada mapel+kelas yang sama.
    # Jadi J1-P1 dan J2-P1 tidak akan menjadi dua data berbeda.
    absen = (
        KehadiranMurid.query
        .filter(
            KehadiranMurid.id_jadwal.in_(id_jadwal_group),
            KehadiranMurid.id_murid == id_murid,
            KehadiranMurid.pertemuan == pertemuan,
            KehadiranMurid.semester == semester,
            KehadiranMurid.tahun_ajaran == tahun_ajaran,
        )
        .first()
    )

    if absen:
        if int(absen.id_jadwal) != int(id_jadwal):
            return jsonify({
                "message": (
                    f"Pertemuan {pertemuan} sudah tercatat pada jadwal lain "
                    "dalam mapel ini. Pilih jadwal sumber yang benar untuk memperbaiki."
                )
            }), 409

        absen.status = status
        absen.semester = semester
        absen.tahun_ajaran = tahun_ajaran
        absen.tanggal = tgl
        # Jika guru mengubah data setelah pernah mengirim, perubahan wajib dikirim ulang.
        absen.status_kirim = False
        db.session.commit()
        return jsonify({"message": "Absensi diperbarui"}), 200

    hadir = KehadiranMurid(
        id_jadwal=id_jadwal,
        id_murid=id_murid,
        semester=semester,
        tahun_ajaran=tahun_ajaran,
        pertemuan=pertemuan,
        status=status,
        tanggal=tgl,
        status_kirim=False
    )
    db.session.add(hadir)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "message": "Absensi pertemuan ini sudah ada, muat ulang data lalu edit data yang tersedia"
        }), 409

    return jsonify({"message": "Absensi tersimpan"}), 201


# =====================================================
# GET ABSEN MURID (PER JADWAL)
# =====================================================
# =====================================================
# GET ABSEN MURID / ORANG TUA (PER JADWAL)
# =====================================================
@kehadiran_bp.route("/kehadiran/murid/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def get_absen_murid(id_jadwal):
    claims = get_jwt()
    role = claims.get("role")

    if role not in ["murid", "orang_tua"]:
        return jsonify({"message": "Akses ditolak"}), 403

    id_murid = claims.get("id_murid")

    if not id_murid:
        return jsonify({"message": "ID murid tidak ditemukan"}), 400

    jadwal, id_jadwal_group = _jadwal_group_ids_by_id(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify([]), 200

    data = (
        KehadiranMurid.query
        .filter(
            KehadiranMurid.id_jadwal.in_(id_jadwal_group),
            KehadiranMurid.id_murid == id_murid,
        )
        .order_by(KehadiranMurid.pertemuan.asc(), KehadiranMurid.tanggal.asc())
        .all()
    )

    return jsonify([
        {
            "id_kehadiran": d.id_kehadiran,
            "id_jadwal": d.id_jadwal,
            "pertemuan": d.pertemuan,
            "status": d.status,
            "semester": d.semester,
            "tahun_ajaran": d.tahun_ajaran,
            "tanggal": str(d.tanggal)
        } for d in data
    ]), 200


# =====================================================
# LAPORAN ABSENSI GURU PER JADWAL (opsional filter pertemuan)
# =====================================================
@kehadiran_bp.route("/guru/absensi/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def laporan_guru(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "ID guru tidak ditemukan"}), 400

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak valid untuk guru ini"}), 403

    jadwal, id_jadwal_group = _jadwal_group_ids_by_id(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify([]), 200

    pertemuan = request.args.get("pertemuan")  # optional

    q = (db.session.query(KehadiranMurid, Murid)
         .join(Murid, Murid.id_murid == KehadiranMurid.id_murid)
         .filter(KehadiranMurid.id_jadwal.in_(id_jadwal_group)))

    if pertemuan:
        q = q.filter(KehadiranMurid.pertemuan == int(pertemuan))

    q = _apply_absensi_semester_tahun_filter(q)

    data = q.order_by(KehadiranMurid.pertemuan, Murid.nama_murid).all()

    result = []
    for absen, murid in data:
        result.append({
            "id_murid": murid.id_murid,
            "nis": murid.nis,
            "nama_murid": murid.nama_murid,
            "pertemuan": absen.pertemuan,
            "status": absen.status,
            "semester": absen.semester,
            "tahun_ajaran": absen.tahun_ajaran,
            "tanggal": str(absen.tanggal)
        })

    return jsonify(result), 200


# =====================================================
# ✅ REKAP ADMIN PER JADWAL (36 pertemuan)
# =====================================================
# =====================================================
# ❌ ROUTE LAMA /absensi (SALAH) -> GANTI jadi rekap by jadwal+tanggal
# =====================================================
@kehadiran_bp.route("/absensi", methods=["GET"])
@jwt_required()
def get_absensi_by_jadwal_tanggal():
    """
    Query:
      - id_jadwal=1
      - tanggal=YYYY-MM-DD (opsional; default hari ini)
    """
    claims = get_jwt()
    role = claims.get("role")
    if role not in ["admin", "guru"]:
        return jsonify({"message": "Akses ditolak"}), 403

    id_jadwal = request.args.get("id_jadwal")
    if not id_jadwal:
        return jsonify({"message": "id_jadwal wajib"}), 400

    tanggal_str = request.args.get("tanggal")
    tgl = date.today()
    if tanggal_str:
        try:
            y, m, d = map(int, tanggal_str.split("-"))
            tgl = date(y, m, d)
        except:
            return jsonify({"message": "Format tanggal harus YYYY-MM-DD"}), 400

    jadwal = Jadwal.query.get(int(id_jadwal))
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify([]), 200

    data = (db.session.query(KehadiranMurid, Murid)
            .join(Murid, Murid.id_murid == KehadiranMurid.id_murid)
            .filter(KehadiranMurid.id_jadwal == int(id_jadwal),
                    KehadiranMurid.tanggal == tgl)
            .order_by(Murid.nama_murid)
            .all())

    return jsonify([
        {
            "id_kehadiran": a.id_kehadiran,
            "id_murid": m.id_murid,
            "nis": m.nis,
            "nama_murid": m.nama_murid,
            "pertemuan": a.pertemuan,
            "status": a.status,
            "semester": a.semester,
            "tahun_ajaran": a.tahun_ajaran,
            "tanggal": str(a.tanggal),
        } for a, m in data
    ]), 200

# =====================================================
# ✅ GURU: LIST PERTEMUAN YANG SUDAH DIINPUT PER JADWAL
# frontend: GET /api/guru/kehadiran/pertemuan/<id_jadwal>
# =====================================================
@kehadiran_bp.route("/guru/kehadiran/pertemuan/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def get_pertemuan_terisi_guru(id_jadwal):
    claims = get_jwt()
    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    if not jadwal_milik_guru(id_jadwal, id_guru):
        return jsonify({"message": "Jadwal tidak valid"}), 403

    jadwal, id_jadwal_group = _jadwal_group_ids_by_id(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify({
            "id_jadwal": id_jadwal,
            "id_jadwal_group": [],
            "pertemuan_terisi": []
        }), 200

    rows_query = (
        db.session.query(KehadiranMurid.pertemuan)
        .filter(KehadiranMurid.id_jadwal.in_(id_jadwal_group))
    )
    rows_query = _apply_absensi_semester_tahun_filter(rows_query)
    rows = (
        rows_query
        .distinct()
        .order_by(KehadiranMurid.pertemuan.asc())
        .all()
    )

    pertemuan_list = [r[0] for r in rows if r[0] is not None]

    return jsonify({
        "id_jadwal": id_jadwal,
        "id_jadwal_group": id_jadwal_group,
        "pertemuan_terisi": pertemuan_list
    }), 200




# =====================================================
# MURID: DETAIL ABSENSI MAPEL (GABUNG J1/J2/J3)
# frontend: GET /murid/absen?id_murid=1&id_jadwal=10
# =====================================================
@kehadiran_bp.route("/murid/absen", methods=["GET"])
@jwt_required()
def murid_absen_mapel():
    claims = get_jwt()
    role = claims.get("role")

    if role not in ["murid", "orang_tua", "admin", "guru"]:
        return jsonify({"message": "Akses ditolak"}), 403

    id_murid = request.args.get("id_murid") or claims.get("id_murid")
    id_jadwal = request.args.get("id_jadwal")

    if not id_murid or not id_jadwal:
        return jsonify({"message": "id_murid dan id_jadwal wajib"}), 400

    jadwal, id_jadwal_group = _jadwal_group_ids_by_id(int(id_jadwal))
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify([]), 200

    rows_query = (
        KehadiranMurid.query
        .filter(
            KehadiranMurid.id_jadwal.in_(id_jadwal_group),
            KehadiranMurid.id_murid == int(id_murid),
        )
    )
    rows_query = _apply_absensi_semester_tahun_filter(rows_query)
    rows = (
        rows_query
        .order_by(KehadiranMurid.pertemuan.asc(), KehadiranMurid.tanggal.asc())
        .all()
    )

    return jsonify([
        {
            "id_kehadiran": r.id_kehadiran,
            "id_jadwal": r.id_jadwal,
            "pertemuan": r.pertemuan,
            "status": r.status,
            "semester": r.semester,
            "tahun_ajaran": r.tahun_ajaran,
            "tanggal": str(r.tanggal),
        }
        for r in rows
    ]), 200


# Endpoint khusus guru dipindahkan ke app/routes/guru.py.

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt

from app import db
from app.models.kelas import Kelas
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.murid import Murid
from app.models.kehadiran_murid import KehadiranMurid

admin_bp = Blueprint("admin", __name__)


# =====================================================
# ADMIN TERIMA ABSENSI DARI GURU (BERDASARKAN ID_JADWAL)
# =====================================================
@admin_bp.route("/admin/absensi", methods=["POST"])
@jwt_required()
def admin_terima_absensi():
    claims = get_jwt()

    if claims.get("role") != "guru":
        return jsonify({"message": "Akses ditolak"}), 403

    id_guru = claims.get("id_guru")
    if not id_guru:
        return jsonify({"message": "id_guru tidak ada di token"}), 400

    data = request.get_json() or {}
    id_jadwal = data.get("id_jadwal")
    id_jadwal_list = data.get("id_jadwal_list") or []
    rekap = data.get("rekap", [])
    semester = data.get("semester") or request.args.get("semester")
    tahun_ajaran = data.get("tahun_ajaran") or data.get("tahun") or request.args.get("tahun_ajaran") or request.args.get("tahun")

    if not id_jadwal:
        return jsonify({"message": "id_jadwal wajib"}), 400

    if not isinstance(rekap, list):
        return jsonify({"message": "rekap harus berupa list"}), 400

    jadwal = Jadwal.query.get(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify({"message": "Jadwal/kelas sudah selesai"}), 403

    # validasi jadwal milik guru login
    cek = JadwalGuru.query.filter_by(
        id_jadwal=id_jadwal,
        id_guru=id_guru
    ).first()

    if not cek:
        return jsonify({"message": "Jadwal bukan milik guru login"}), 403

    # Data absensi memang tersimpan saat guru input, tetapi admin hanya boleh
    # melihat data yang sudah diberi tanda status_kirim=True melalui tombol kirim.
    semester_norm = None
    if semester and str(semester).strip().lower() not in ["all", "ganjilgenap", "1 tahun ajaran", "setahun"]:
        semester_norm = _normalisasi_semester_kehadiran(semester)
    tahun_ajaran = tahun_ajaran or _tahun_ajaran_jadwal(jadwal)

    jadwal_group = _jadwal_group_ids(jadwal)
    rows_query = KehadiranMurid.query.filter(KehadiranMurid.id_jadwal.in_(jadwal_group))
    if semester_norm:
        rows_query = rows_query.filter(KehadiranMurid.semester == semester_norm)
    if tahun_ajaran:
        rows_query = rows_query.filter(KehadiranMurid.tahun_ajaran == tahun_ajaran)

    awal, akhir = _pertemuan_range_from_mode(semester)
    rows_query = rows_query.filter(KehadiranMurid.pertemuan >= awal, KehadiranMurid.pertemuan <= akhir)
    rows_terkirim = rows_query.all()
    if not rows_terkirim:
        return jsonify({
            "message": "Belum ada data absensi pada jadwal dan semester-tahun ajaran ini"
        }), 404

    for row in rows_terkirim:
        row.status_kirim = True

    db.session.commit()

    return jsonify({
        "message": "Rekap diterima admin",
        "id_jadwal": id_jadwal,
        "id_jadwal_group": id_jadwal_list or jadwal_group,
        "jumlah": len(rekap),
        "jumlah_data_terkirim": len(rows_terkirim)
    }), 201


# =====================================================
# ADMIN LIHAT REKAP ABSENSI BERDASARKAN ID_JADWAL
# =====================================================
@admin_bp.route("/admin/rekap-absensi/<int:id_jadwal>", methods=["GET"])
@jwt_required()
def get_rekap_absensi_admin_by_jadwal(id_jadwal):
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"message": "Akses ditolak"}), 403

    jadwal, id_jadwal_group = _jadwal_group_ids_by_id(id_jadwal)
    if not jadwal:
        return jsonify({"message": "Jadwal tidak ditemukan"}), 404
    if not _jadwal_kelas_aktif(jadwal):
        return jsonify([]), 200

    semester = request.args.get("semester")
    tahun_ajaran = request.args.get("tahun_ajaran") or request.args.get("tahun")

    return jsonify(_rekap_absensi_mapel(jadwal, id_jadwal_group, only_terkirim=True, semester=semester, tahun_ajaran=tahun_ajaran)), 200
