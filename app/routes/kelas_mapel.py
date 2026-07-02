from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import datetime, time

from app.extensions import db
from app.models.kelas import Kelas
from app.models.mata_pelajaran import MataPelajaran
from app.models.jadwal import Jadwal
from app.models.murid import Murid
from app.models.jadwal_murid import jadwal_murid
from app.models.murid_tingkat import MuridTingkat
from app.models.kelas_mapel import kelas_mapel

kelas_mapel_bp = Blueprint("kelas_mapel", __name__)

HARI_VALID = {
    "senin": "Senin",
    "selasa": "Selasa",
    "rabu": "Rabu",
    "kamis": "Kamis",
    "jumat": "Jumat",
    "jum'at": "Jumat",
    "jum’at": "Jumat",
    "sabtu": "Sabtu",
    "minggu": "Minggu",
}

HARI_ORDER = {
    "Senin": 1,
    "Selasa": 2,
    "Rabu": 3,
    "Kamis": 4,
    "Jumat": 5,
    "Sabtu": 6,
    "Minggu": 7,
}


def _to_int(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _parse_jam(value):
    if value is None:
        return None

    if isinstance(value, time):
        return value

    text = str(value).strip()

    if not text:
        return None

    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except Exception:
            pass

    return None


def _normalisasi_hari(value):
    if value is None:
        return None

    text = str(value).strip().lower().replace("’", "'")

    if text in ["jum'at", "jumat'", "jumat"]:
        text = "jumat"

    return HARI_VALID.get(text)


def _hari_sort_value(hari):
    hari_normal = _normalisasi_hari(hari) or str(hari or "").strip()
    return HARI_ORDER.get(hari_normal, 99)


def _is_bentrok(jadwal_lama, jam_mulai_baru, jam_selesai_baru):
    return (
        jadwal_lama.jam_mulai < jam_selesai_baru
        and jam_mulai_baru < jadwal_lama.jam_selesai
    )


def _jadwal_baru_bentrok(a, b):
    if a["hari"] != b["hari"]:
        return False

    return a["jam_mulai"] < b["jam_selesai"] and b["jam_mulai"] < a["jam_selesai"]


def _ambil_jadwal_list(data):
    jadwal_list = (
        data.get("jadwal_list")
        or data.get("jadwalList")
        or data.get("jadwal")
        or data.get("jadwals")
    )

    if isinstance(jadwal_list, list) and len(jadwal_list) > 0:
        return jadwal_list

    return [
        {
            "hari": data.get("hari"),
            "jam_mulai": data.get("jam_mulai") or data.get("jamMulai"),
            "jam_selesai": data.get("jam_selesai") or data.get("jamSelesai"),
        }
    ]


@kelas_mapel_bp.route("/kelas/mapel/jadwal", methods=["POST"])
@jwt_required()
def add_mapel_with_jadwal():
    claims = get_jwt()

    if claims.get("role") != "admin":
        return jsonify({"msg": "Hanya admin"}), 403

    data = request.get_json(silent=True) or {}

    print("========== BACKEND ADD MAPEL + JADWAL ==========")
    print("DATA MASUK:", data)

    id_kelas = _to_int(data.get("id_kelas") or data.get("kelas_id"))
    id_mapel_input = _to_int(data.get("id_mapel") or data.get("mapel_id"))

    nama_mapel = (
        data.get("nama_mapel")
        or data.get("mapel")
        or data.get("nama")
        or ""
    )
    nama_mapel = str(nama_mapel).strip()

    print("ID KELAS:", id_kelas)
    print("ID MAPEL INPUT:", id_mapel_input)
    print("NAMA MAPEL:", nama_mapel)

    if not id_kelas:
        return jsonify({"msg": "id_kelas wajib diisi"}), 400

    if not id_mapel_input and not nama_mapel:
        return jsonify({"msg": "id_mapel atau nama_mapel wajib diisi"}), 400

    kelas = Kelas.query.get(id_kelas)
    if not kelas:
        return jsonify({"msg": "Kelas tidak ditemukan"}), 404

    status_kelas = str(getattr(kelas, "status", "aktif") or "aktif").lower()

    if status_kelas in ["selesai", "arsip", "nonaktif", "non-aktif"]:
        return jsonify({
            "msg": "Kelas sudah selesai/arsip, tidak bisa menambah mapel atau jadwal"
        }), 400

    jadwal_input = _ambil_jadwal_list(data)

    print("JADWAL INPUT:", jadwal_input)

    if not jadwal_input:
        return jsonify({"msg": "Minimal 1 jadwal wajib diisi"}), 400

    if len(jadwal_input) > 3:
        return jsonify({"msg": "Maksimal 3 pertemuan dalam 1 minggu"}), 400

    jadwal_baru = []

    for idx, row in enumerate(jadwal_input, start=1):
        if not isinstance(row, dict):
            return jsonify({"msg": f"Format jadwal pertemuan {idx} tidak valid"}), 400

        hari_normal = _normalisasi_hari(row.get("hari"))
        jam_mulai_raw = row.get("jam_mulai") or row.get("jamMulai")
        jam_selesai_raw = row.get("jam_selesai") or row.get("jamSelesai")

        jm = _parse_jam(jam_mulai_raw)
        js = _parse_jam(jam_selesai_raw)

        print(f"PERTEMUAN INPUT {idx}:")
        print("hari:", hari_normal)
        print("jam_mulai:", jm)
        print("jam_selesai:", js)

        if not hari_normal or not jm or not js:
            return jsonify({
                "msg": f"Data jadwal pertemuan {idx} belum lengkap",
                "detail": {
                    "hari": row.get("hari"),
                    "jam_mulai": jam_mulai_raw,
                    "jam_selesai": jam_selesai_raw,
                }
            }), 400

        if jm >= js:
            return jsonify({
                "msg": f"Jam mulai pertemuan {idx} harus lebih kecil dari jam selesai"
            }), 400

        jadwal_baru.append({
            "hari": hari_normal,
            "jam_mulai": jm,
            "jam_selesai": js,
        })

    # Urutkan jadwal agar J1/J2/J3 benar.
    # Contoh: Senin = J1, Rabu = J2, Jumat = J3.
    jadwal_baru.sort(
        key=lambda row: (
            _hari_sort_value(row["hari"]),
            row["jam_mulai"].strftime("%H:%M"),
            row["jam_selesai"].strftime("%H:%M"),
        )
    )

    print("JADWAL SETELAH SORTING:")
    for idx, row in enumerate(jadwal_baru, start=1):
        print(
            f"J{idx}: {row['hari']} "
            f"{row['jam_mulai'].strftime('%H:%M')}-"
            f"{row['jam_selesai'].strftime('%H:%M')}"
        )

    # Cek bentrok antar jadwal baru.
    for i in range(len(jadwal_baru)):
        for j in range(i + 1, len(jadwal_baru)):
            if _jadwal_baru_bentrok(jadwal_baru[i], jadwal_baru[j]):
                return jsonify({
                    "msg": f"Jadwal J{i + 1} dan J{j + 1} bentrok pada hari dan jam yang sama",
                    "detail": {
                        "jadwal_1": {
                            "hari": jadwal_baru[i]["hari"],
                            "jam_mulai": jadwal_baru[i]["jam_mulai"].strftime("%H:%M"),
                            "jam_selesai": jadwal_baru[i]["jam_selesai"].strftime("%H:%M"),
                        },
                        "jadwal_2": {
                            "hari": jadwal_baru[j]["hari"],
                            "jam_mulai": jadwal_baru[j]["jam_mulai"].strftime("%H:%M"),
                            "jam_selesai": jadwal_baru[j]["jam_selesai"].strftime("%H:%M"),
                        },
                    }
                }), 409

    # Cek bentrok dengan jadwal lama di kelas yang sama.
    # Ini dilakukan sebelum membuat mapel baru supaya kalau bentrok,
    # tidak ada mapel baru yang terlanjur dibuat.
    for idx, row in enumerate(jadwal_baru, start=1):
        jadwal_hari_ini = Jadwal.query.filter_by(
            id_kelas=id_kelas,
            hari=row["hari"],
            status="aktif",
        ).all()

        for jadwal in jadwal_hari_ini:
            if _is_bentrok(jadwal, row["jam_mulai"], row["jam_selesai"]):
                return jsonify({
                    "msg": f"Jadwal J{idx} bentrok dengan jadwal lain pada kelas dan hari yang sama",
                    "detail": {
                        "hari": row["hari"],
                        "jam_mulai": row["jam_mulai"].strftime("%H:%M"),
                        "jam_selesai": row["jam_selesai"].strftime("%H:%M"),
                        "jadwal_lama": {
                            "id_jadwal": jadwal.id_jadwal,
                            "hari": jadwal.hari,
                            "jam_mulai": jadwal.jam_mulai.strftime("%H:%M") if jadwal.jam_mulai else None,
                            "jam_selesai": jadwal.jam_selesai.strftime("%H:%M") if jadwal.jam_selesai else None,
                        }
                    }
                }), 409

    id_tingkat = getattr(kelas, "id_tingkat", None)

    try:
        # Ambil atau buat mapel.
        if id_mapel_input:
            mapel = MataPelajaran.query.get(id_mapel_input)

            if not mapel:
                return jsonify({"msg": "Mata pelajaran tidak ditemukan"}), 404
        else:
            mapel = MataPelajaran.query.filter_by(
                nama_mapel=nama_mapel,
                id_tingkat=id_tingkat,
            ).first()

            if not mapel:
                mapel = MataPelajaran(
                    nama_mapel=nama_mapel,
                    id_tingkat=id_tingkat,
                )
                db.session.add(mapel)
                db.session.flush()

        id_mapel = mapel.id_mapel

        # Tambahkan relasi kelas-mapel jika belum ada.
        relasi_sudah_ada = db.session.execute(
            db.select(kelas_mapel.c.id_kelas)
            .where(
                kelas_mapel.c.id_kelas == id_kelas,
                kelas_mapel.c.id_mapel == id_mapel,
            )
            .limit(1)
        ).first()

        if not relasi_sudah_ada:
            db.session.execute(
                kelas_mapel.insert().values(
                    id_kelas=id_kelas,
                    id_mapel=id_mapel,
                )
            )

        jadwal_tersimpan = []

        for row in jadwal_baru:
            jadwal = Jadwal(
                id_kelas=id_kelas,
                id_mapel=id_mapel,
                hari=row["hari"],
                jam_mulai=row["jam_mulai"],
                jam_selesai=row["jam_selesai"],
                status="aktif",
            )

            db.session.add(jadwal)
            jadwal_tersimpan.append(jadwal)

        # Pastikan ID jadwal tersedia sebelum sinkron murid.
        db.session.flush()

        # Murid yang sudah berada di kelas ini otomatis tersambung ke semua
        # jadwal baru pada mapel tersebut, termasuk mapel dengan 2 atau 3 jadwal.
        murid_kelas = (
            db.session.query(Murid)
            .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
            .filter(
                MuridTingkat.id_kelas == id_kelas,
                MuridTingkat.status == "aktif",
            )
            .all()
        )

        if not murid_kelas:
            murid_kelas = Murid.query.filter_by(id_kelas=id_kelas).all()
        for murid in murid_kelas:
            if mapel not in murid.mapel:
                murid.mapel.append(mapel)

            for jadwal in jadwal_tersimpan:
                relasi_sudah_ada = db.session.execute(
                    db.select(jadwal_murid.c.id_jadwal).where(
                        jadwal_murid.c.id_jadwal == jadwal.id_jadwal,
                        jadwal_murid.c.id_murid == murid.id_murid,
                    ).limit(1)
                ).first()

                if not relasi_sudah_ada:
                    db.session.execute(
                        jadwal_murid.insert().values(
                            id_jadwal=jadwal.id_jadwal,
                            id_murid=murid.id_murid,
                        )
                    )

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print("ERROR SIMPAN MAPEL + JADWAL:", e)
        return jsonify({
            "msg": "Gagal menyimpan mapel dan jadwal",
            "error": str(e),
        }), 500

    id_jadwal_list = [j.id_jadwal for j in jadwal_tersimpan]

    return jsonify({
        "msg": "Mapel dan jadwal berhasil ditambahkan",
        "id_kelas": id_kelas,
        "id_mapel": id_mapel,
        "nama_mapel": mapel.nama_mapel,
        "jumlah_jadwal": len(jadwal_tersimpan),
        "id_jadwal_list": id_jadwal_list,
        "jadwal": [
            {
                "urutan": idx + 1,
                "kode": f"J{idx + 1}",
                "id_jadwal": j.id_jadwal,
                "hari": j.hari,
                "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else None,
                "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else None,
            }
            for idx, j in enumerate(jadwal_tersimpan)
        ],
    }), 201