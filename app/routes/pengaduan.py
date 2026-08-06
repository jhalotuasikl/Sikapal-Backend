import json
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import text

from app.extensions import db
from app.models.guru import Guru
from app.models.murid import Murid
from app.models.pengaduan import Pengaduan
from app.models.periode_akademik import PeriodeAkademik

pengaduan_bp = Blueprint("pengaduan", __name__)


SUB_KATEGORI_VALID = {
    "pengaduan": {
        "akademik": [
            "Materi pembelajaran sulit dipahami",
            "Metode mengajar kurang efektif",
            "Guru tidak masuk atau tidak mengajar",
            "Tugas terlalu banyak atau tidak sesuai",
            "Jadwal pembelajaran bermasalah",
            "Kegiatan praktik tidak terlaksana",
        ],
        "absensi": [
            "Kehadiran tercatat tidak sesuai",
            "Status hadir berubah menjadi alpa",
            "Izin atau sakit tidak tercatat",
            "Absensi belum diinput oleh guru",
            "Data kehadiran ganda",
            "Rekap kehadiran tidak sesuai",
        ],
        "nilai": [
            "Nilai belum dimasukkan",
            "Nilai tidak sesuai hasil pekerjaan",
            "Kesalahan input nilai",
            "Nilai tugas atau ujian tidak lengkap",
            "Kriteria penilaian tidak jelas",
            "Nilai tidak dapat dilihat di aplikasi",
        ],
        "bullying": [
            "Bullying verbal atau penghinaan",
            "Bullying fisik",
            "Pengucilan atau bullying sosial",
            "Ancaman atau intimidasi",
            "Konflik antarsiswa",
            "Bullying melalui media sosial",
        ],
        "fasilitas": [
            "Ruang kelas rusak atau tidak nyaman",
            "Toilet dan sanitasi bermasalah",
            "Peralatan praktik rusak atau kurang",
            "Komputer atau internet bermasalah",
            "Kebersihan lingkungan sekolah",
            "Air, listrik, atau penerangan bermasalah",
        ],
        "lainnya": [
            "Pelayanan administrasi",
            "Masalah akun atau aplikasi",
            "Keamanan lingkungan sekolah",
            "Kegiatan ekstrakurikuler",
            "Kantin atau konsumsi sekolah",
            "Pengaduan lainnya",
        ],
    },
    "aspirasi": {
        "akademik": [
            "Penambahan metode pembelajaran interaktif",
            "Penambahan kegiatan praktik",
            "Program bimbingan belajar",
            "Penambahan materi atau sumber belajar",
            "Kelas tambahan atau pendalaman materi",
            "Pengembangan pembelajaran digital",
        ],
        "absensi": [
            "Pengingat jadwal absensi",
            "Notifikasi ketika tidak hadir",
            "Perbaikan tampilan rekap kehadiran",
            "Pengajuan izin melalui aplikasi",
            "Konfirmasi absensi oleh siswa",
            "Rekap kehadiran untuk orang tua",
        ],
        "nilai": [
            "Notifikasi ketika nilai diterbitkan",
            "Penjelasan rincian komponen nilai",
            "Fitur pengajuan koreksi nilai",
            "Grafik perkembangan nilai",
            "Penambahan penilaian praktik",
            "Transparansi kriteria penilaian",
        ],
        "bullying": [
            "Program pencegahan bullying",
            "Layanan konseling siswa",
            "Kotak laporan rahasia atau anonim",
            "Kegiatan edukasi antikekerasan",
            "Program mediasi konflik",
            "Pendampingan korban bullying",
        ],
        "fasilitas": [
            "Penambahan fasilitas ruang kelas",
            "Perbaikan toilet dan sanitasi",
            "Penambahan alat praktik",
            "Peningkatan jaringan internet",
            "Penambahan fasilitas olahraga",
            "Penambahan ruang belajar atau istirahat",
        ],
        "lainnya": [
            "Pengembangan kegiatan ekstrakurikuler",
            "Peningkatan pelayanan administrasi",
            "Pengembangan aplikasi sekolah",
            "Program kebersihan dan lingkungan",
            "Peningkatan keamanan sekolah",
            "Aspirasi atau inovasi lainnya",
        ],
    },
}

GURU_SUB_KATEGORI_VALID = {
    "pengaduan": {
        "akademik_pembelajaran": [
            "Jadwal mengajar bermasalah",
            "Pembagian mata pelajaran tidak sesuai",
            "Bentrok jadwal",
            "Jumlah jam mengajar",
            "Kelas atau rombel bermasalah",
            "Kegiatan pembelajaran",
        ],
        "data_siakad": [
            "Data guru salah",
            "Data murid salah",
            "Kelas atau tingkat tidak sesuai",
            "Mata pelajaran tidak tampil",
            "Nilai bermasalah",
            "Absensi bermasalah",
            "Periode akademik tidak sesuai",
        ],
        "sistem_aplikasi": [
            "Tidak dapat login",
            "Aplikasi lambat",
            "Tombol tidak berfungsi",
            "Gagal menyimpan",
            "Gagal mengirim laporan",
            "Data tidak tersinkron",
            "Ekspor atau unduh gagal",
        ],
        "sarana_prasarana": [
            "Ruang kelas",
            "Laboratorium",
            "Perangkat pembelajaran",
            "Komputer",
            "Proyektor",
            "Jaringan internet",
            "Kebersihan atau keamanan ruangan",
        ],
        "kesiswaan": [
            "Perilaku murid",
            "Kedisiplinan",
            "Ketidakhadiran berulang",
            "Kendala belajar",
            "Konflik antarmurid",
            "Kebutuhan pendampingan",
        ],
        "kepegawaian_tugas_guru": [
            "Beban kerja",
            "Penugasan tambahan",
            "Pembagian jadwal",
            "Izin atau sakit",
            "Administrasi guru",
            "Komunikasi internal",
        ],
        "etika_lingkungan_kerja": [
            "Perlakuan tidak pantas",
            "Intimidasi",
            "Konflik kerja",
            "Pelanggaran etika",
            "Keamanan",
            "Masalah sensitif lainnya",
        ],
        "lainnya": ["Masalah yang tidak termasuk kategori yang tersedia"],
    },
    "aspirasi": {
        "pengembangan_pembelajaran": [
            "Metode belajar",
            "Media pembelajaran",
            "Evaluasi",
            "Kegiatan praktik",
            "Pembelajaran digital",
        ],
        "pengembangan_siakad": [
            "Fitur baru",
            "Perbaikan tampilan",
            "Penyederhanaan alur",
            "Laporan tambahan",
            "Notifikasi",
        ],
        "peningkatan_fasilitas": [
            "Ruang kelas",
            "Laboratorium",
            "Internet",
            "Perangkat",
            "Perpustakaan",
        ],
        "program_kesiswaan": [
            "Disiplin",
            "Pendampingan",
            "Kegiatan siswa",
            "Prestasi",
            "Konseling",
        ],
        "pengembangan_guru": [
            "Pelatihan",
            "Sertifikasi",
            "Workshop",
            "Forum diskusi",
            "Evaluasi kerja",
        ],
        "kebijakan_sekolah": [
            "Jadwal",
            "Pembagian tugas",
            "Administrasi",
            "Komunikasi",
            "Pelayanan internal",
        ],
        "lainnya": ["Usulan lain untuk pengembangan sekolah"],
    },
}

TARGET_PENANGANAN = {
    "akademik_pembelajaran": "Wakil Kepala Sekolah Bidang Kurikulum",
    "data_siakad": "Admin atau Operator SI-KAPAL",
    "sistem_aplikasi": "Admin atau Operator SI-KAPAL",
    "sarana_prasarana": "Bagian Sarana dan Prasarana",
    "kesiswaan": "Wali Kelas, BK, atau Bidang Kesiswaan",
    "kepegawaian_tugas_guru": "Tata Usaha atau Pimpinan Sekolah",
    "etika_lingkungan_kerja": "Kepala Sekolah atau Admin Khusus",
    "pengembangan_pembelajaran": "Wakil Kepala Sekolah Bidang Kurikulum",
    "pengembangan_siakad": "Admin atau Operator SI-KAPAL",
    "peningkatan_fasilitas": "Bagian Sarana dan Prasarana",
    "program_kesiswaan": "Bidang Kesiswaan",
    "pengembangan_guru": "Pimpinan Sekolah",
    "kebijakan_sekolah": "Pimpinan Sekolah",
    "lainnya": "Admin Sekolah",
}

STATUS_VALID = [
    "menunggu",
    "dikirim",
    "ditinjau",
    "diproses",
    "menunggu_informasi",
    "selesai",
    "ditolak",
]


def _to_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _get_orang_tua_from_db(identity=None, id_ortu=None):
    try:
        if id_ortu:
            row = db.session.execute(
                text(
                    "SELECT id_ortu, id_murid FROM orang_tua "
                    "WHERE id_ortu = :id_ortu LIMIT 1"
                ),
                {"id_ortu": id_ortu},
            ).mappings().first()
            if row:
                return _to_int(row.get("id_ortu")), _to_int(row.get("id_murid"))
        if identity:
            row = db.session.execute(
                text(
                    "SELECT id_ortu, id_murid FROM orang_tua "
                    "WHERE id_user = :id_user LIMIT 1"
                ),
                {"id_user": identity},
            ).mappings().first()
            if row:
                return _to_int(row.get("id_ortu")), _to_int(row.get("id_murid"))
    except Exception:
        pass
    return None, None


def get_pelapor_from_token(claims, identity):
    role = str(claims.get("role") or "").lower()
    if role == "murid":
        murid = Murid.query.filter_by(id_user=identity).first()
        id_murid = _to_int(claims.get("id_murid")) or (
            murid.id_murid if murid else None
        )
        if not id_murid:
            return None, None, None, None, jsonify(
                {"message": "Data murid tidak ditemukan. Silakan masuk ulang."}
            ), 404
        return id_murid, None, None, "murid", None, None

    if role in ["orang_tua", "ortu", "orangtua"]:
        id_ortu = _to_int(claims.get("id_ortu"))
        id_murid = _to_int(claims.get("id_murid"))
        if not id_ortu or not id_murid:
            db_id_ortu, db_id_murid = _get_orang_tua_from_db(identity, id_ortu)
            id_ortu = id_ortu or db_id_ortu
            id_murid = id_murid or db_id_murid
        if not id_ortu:
            return None, None, None, None, jsonify(
                {"message": "Data orang tua tidak ditemukan. Silakan masuk ulang."}
            ), 404
        if not id_murid:
            return None, None, None, None, jsonify(
                {"message": "Data anak yang terhubung dengan akun tidak ditemukan."}
            ), 404
        return id_murid, id_ortu, None, "orang_tua", None, None

    if role == "guru":
        guru = Guru.query.filter_by(id_user=identity).first()
        id_guru = _to_int(claims.get("id_guru")) or (
            guru.id_guru if guru else None
        )
        if not id_guru:
            return None, None, None, None, jsonify(
                {"message": "Data guru tidak ditemukan. Silakan masuk ulang."}
            ), 404
        return None, None, id_guru, "guru", None, None

    return None, None, None, None, jsonify(
        {"message": "Akun ini tidak memiliki akses ke layanan pengaduan."}
    ), 403


def _samarkan_jika_anonim(item, row):
    if item.mode_pelaporan == "anonim":
        for key in [
            "nama_murid",
            "nama_ortu",
            "nama_guru",
            "nis",
            "nip",
            "nomor_telepon",
            "no_hp",
            "id_murid",
            "id_ortu",
            "id_guru",
            "id_kelas",
            "nama_kelas",
            "tingkat",
        ]:
            row[key] = None
        row["pelapor_display"] = "Anonim"
        metadata = dict(row.get("metadata_pelapor") or {})
        metadata.pop("nama_guru", None)
        metadata.pop("nip", None)
        row["metadata_pelapor"] = metadata
    return row


def _teacher_metadata(id_guru, data):
    guru = Guru.query.get(id_guru)
    periode = PeriodeAkademik.aktif()
    return {
        "nama_guru": guru.nama_guru if guru else None,
        "nip": guru.nip if guru else None,
        "tahun_ajaran": periode.tahun_ajaran if periode else None,
        "semester": periode.semester if periode else None,
        "kelas": data.get("kelas"),
        "mata_pelajaran": data.get("mata_pelajaran"),
        "jadwal": data.get("jadwal"),
        "perangkat": data.get("perangkat"),
        "versi_aplikasi": data.get("versi_aplikasi"),
        "dikirim_pada": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


@pengaduan_bp.route("/pengaduan", methods=["POST"])
@jwt_required()
def create_pengaduan():
    claims = get_jwt()
    identity = get_jwt_identity()
    id_murid, id_ortu, id_guru, tipe, error, code = get_pelapor_from_token(
        claims, identity
    )
    if error:
        return error, code

    data = request.get_json(silent=True) or {}
    jenis = str(data.get("jenis_laporan") or "pengaduan").strip().lower()
    mode = str(data.get("mode_pelaporan") or "").strip().lower()
    kategori = str(data.get("kategori_pengaduan") or "").strip()
    sub = str(data.get("sub_kategori") or "").strip()
    isi = str(data.get("isi_pengaduan") or "").strip()

    if jenis not in ["pengaduan", "aspirasi"]:
        return jsonify({"message": "Pilih jenis laporan Pengaduan atau Aspirasi."}), 400
    if mode not in ["terbuka", "rahasia", "anonim"]:
        return jsonify({"message": "Pilih mode laporan Terbuka, Rahasia, atau Anonim."}), 400
    if not kategori:
        return jsonify({"message": "Kategori laporan wajib dipilih."}), 400
    if not sub:
        return jsonify({"message": "Subkategori laporan wajib dipilih."}), 400
    if len(isi) < 10:
        return jsonify({"message": "Isi laporan minimal 10 karakter agar dapat ditindaklanjuti."}), 400

    pilihan = GURU_SUB_KATEGORI_VALID if tipe == "guru" else SUB_KATEGORI_VALID
    sub_valid = pilihan.get(jenis, {}).get(kategori, [])
    if not sub_valid:
        return jsonify({"message": "Kategori tidak sesuai dengan jenis laporan yang dipilih."}), 400
    if sub not in sub_valid:
        return jsonify({"message": "Subkategori tidak sesuai dengan kategori laporan."}), 400
    if tipe == "guru" and mode == "anonim" and kategori != "etika_lingkungan_kerja":
        return jsonify({
            "message": "Mode anonim untuk guru hanya tersedia pada kategori Etika dan Lingkungan Kerja. Gunakan mode Rahasia untuk laporan lainnya."
        }), 400

    metadata = _teacher_metadata(id_guru, data) if tipe == "guru" else {}
    item = Pengaduan(
        id_murid=id_murid,
        id_ortu=id_ortu,
        id_guru=id_guru,
        tipe_pelapor=tipe,
        jenis_laporan=jenis,
        mode_pelaporan=mode,
        kategori_pengaduan=kategori,
        sub_kategori=sub,
        isi_pengaduan=isi,
        tujuan_penanganan=(TARGET_PENANGANAN.get(kategori) if tipe == "guru" else "Admin Sekolah"),
        metadata_pelapor=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        lampiran=str(data.get("lampiran") or "").strip() or None,
        status="dikirim" if tipe == "guru" else "menunggu",
    )
    try:
        db.session.add(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"message": "Laporan gagal disimpan. Periksa koneksi lalu coba kembali."}), 500

    label = "Aspirasi" if jenis == "aspirasi" else "Pengaduan"
    return jsonify({"message": f"{label} berhasil dikirim.", "data": item.to_dict()}), 201


@pengaduan_bp.route("/pengaduan/saya", methods=["GET"])
@jwt_required()
def get_pengaduan_saya():
    claims = get_jwt()
    identity = get_jwt_identity()
    id_murid, id_ortu, id_guru, tipe, error, code = get_pelapor_from_token(
        claims, identity
    )
    if error:
        return error, code

    q = Pengaduan.query.filter(Pengaduan.tipe_pelapor == tipe)
    jenis = request.args.get("jenis_laporan")
    if jenis in ["pengaduan", "aspirasi"]:
        q = q.filter(Pengaduan.jenis_laporan == jenis)
    if tipe == "orang_tua":
        q = q.filter(Pengaduan.id_ortu == id_ortu)
    elif tipe == "guru":
        q = q.filter(Pengaduan.id_guru == id_guru)
    else:
        q = q.filter(Pengaduan.id_murid == id_murid)
    data = q.order_by(Pengaduan.tanggal_pengaduan.desc(), Pengaduan.id_pengaduan.desc()).all()
    return jsonify([row.to_dict() for row in data]), 200


@pengaduan_bp.route("/admin/pengaduan", methods=["GET"])
@jwt_required()
def get_semua_pengaduan():
    if get_jwt().get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat melihat seluruh laporan."}), 403
    q = Pengaduan.query
    status = request.args.get("status")
    kategori = request.args.get("kategori")
    jenis = request.args.get("jenis_laporan")
    tipe = request.args.get("tipe_pelapor")
    if status:
        q = q.filter(Pengaduan.status == status)
    if kategori:
        q = q.filter(Pengaduan.kategori_pengaduan == kategori)
    if jenis in ["pengaduan", "aspirasi"]:
        q = q.filter(Pengaduan.jenis_laporan == jenis)
    if tipe in ["murid", "orang_tua", "guru"]:
        q = q.filter(Pengaduan.tipe_pelapor == tipe)
    rows = q.order_by(Pengaduan.tanggal_pengaduan.desc(), Pengaduan.id_pengaduan.desc()).all()
    return jsonify([_samarkan_jika_anonim(row, row.to_dict()) for row in rows]), 200


@pengaduan_bp.route("/admin/pengaduan/<int:id_pengaduan>", methods=["GET"])
@jwt_required()
def detail_pengaduan(id_pengaduan):
    if get_jwt().get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat membuka detail laporan."}), 403
    item = Pengaduan.query.get(id_pengaduan)
    if not item:
        return jsonify({"message": "Laporan tidak ditemukan."}), 404
    return jsonify(_samarkan_jika_anonim(item, item.to_dict())), 200


@pengaduan_bp.route("/admin/pengaduan/<int:id_pengaduan>", methods=["PUT"])
@jwt_required()
def update_pengaduan(id_pengaduan):
    if get_jwt().get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat memperbarui laporan."}), 403
    item = Pengaduan.query.get(id_pengaduan)
    if not item:
        return jsonify({"message": "Laporan tidak ditemukan."}), 404
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").strip()
    catatan = str(data.get("catatan_admin") or "").strip()
    if status and status not in STATUS_VALID:
        return jsonify({"message": "Status tindak lanjut tidak valid."}), 400
    if status in ["ditolak", "menunggu_informasi"] and len(catatan) < 5:
        return jsonify({"message": "Catatan admin minimal 5 karakter untuk status tersebut."}), 400
    if not status and "catatan_admin" not in data:
        return jsonify({"message": "Tidak ada perubahan yang dikirim."}), 400
    if status:
        item.status = status
    if "catatan_admin" in data:
        item.catatan_admin = catatan or None
    item.tanggal_ditindaklanjuti = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"message": "Perubahan gagal disimpan. Silakan coba kembali."}), 500
    return jsonify({"message": "Tindak lanjut berhasil diperbarui.", "data": item.to_dict()}), 200


@pengaduan_bp.route("/pengaduan/<int:id_pengaduan>", methods=["DELETE"])
@jwt_required()
def delete_pengaduan_saya(id_pengaduan):
    claims = get_jwt()
    identity = get_jwt_identity()
    id_murid, id_ortu, id_guru, tipe, error, code = get_pelapor_from_token(
        claims, identity
    )
    if error:
        return error, code
    q = Pengaduan.query.filter(
        Pengaduan.id_pengaduan == id_pengaduan,
        Pengaduan.tipe_pelapor == tipe,
    )
    if tipe == "orang_tua":
        q = q.filter(Pengaduan.id_ortu == id_ortu)
    elif tipe == "guru":
        q = q.filter(Pengaduan.id_guru == id_guru)
    else:
        q = q.filter(Pengaduan.id_murid == id_murid)
    item = q.first()
    if not item:
        return jsonify({"message": "Laporan tidak ditemukan atau bukan milik akun ini."}), 404
    if item.status not in ["menunggu", "dikirim"]:
        return jsonify({"message": "Laporan yang sudah ditinjau tidak dapat dihapus."}), 400
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Laporan berhasil dihapus."}), 200


@pengaduan_bp.route("/admin/pengaduan/<int:id_pengaduan>", methods=["DELETE"])
@jwt_required()
def delete_pengaduan_admin(id_pengaduan):
    if get_jwt().get("role") != "admin":
        return jsonify({"message": "Hanya admin yang dapat menghapus laporan."}), 403
    item = Pengaduan.query.get(id_pengaduan)
    if not item:
        return jsonify({"message": "Laporan tidak ditemukan."}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Laporan berhasil dihapus."}), 200
