from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required, verify_jwt_in_request
from sqlalchemy import func, or_

from app.extensions import db
from app.models.guru import Guru
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.kehadiran_guru import KehadiranGuru
from app.models.kehadiran_murid import KehadiranMurid
from app.models.kelas import Kelas
from app.models.kelas_mapel import kelas_mapel
from app.models.mata_pelajaran import MataPelajaran
from app.models.mengajar import LaporanMengajar
from app.models.monitoring import LaporanMonitoring
from app.models.murid import Murid
from app.models.murid_tingkat import MuridTingkat
from app.models.orang_tua_models import OrangTua
from app.models.periode_akademik import PeriodeAkademik
from app.models.tingkat import Tingkat
from app.models.user import User


master_data_bp = Blueprint("master_data", __name__)


@master_data_bp.before_request
def _guard_admin_master_data():
    if request.method == "OPTIONS":
        return None
    verify_jwt_in_request()
    if get_jwt().get("role") != "admin":
        return jsonify({"message": "Akses khusus admin"}), 403
    return None


def _text(value, default="-"):
    text = str(value if value is not None else "").strip()
    return text if text and text.lower() != "none" else default


def _status(value, default="aktif"):
    return _text(value, default).lower().replace("_", " ")


def _time(value):
    return value.strftime("%H:%M") if value else "-"


def _user_status(id_user):
    if not id_user:
        return "aktif"
    user = User.query.get(id_user)
    return _status(getattr(user, "status", "aktif"), "aktif") if user else "aktif"


def _tingkat_name(tingkat):
    if not tingkat:
        return "-"
    value = _text(getattr(tingkat, "pangkat", None))
    return value if value.lower().startswith("tingkat") else f"Tingkat {value}"


def _kelas_payload(kelas):
    return {
        "id": kelas.id_kelas,
        "nama": kelas.nama_kelas,
        "tingkat": _tingkat_name(kelas.tingkat),
        "tahun_ajaran": kelas.tahun_ajaran,
        "status": _status(getattr(kelas, "status", None)),
    }


def _jadwal_payload(jadwal):
    return {
        "id": jadwal.id_jadwal,
        "nama": f"{_text(getattr(jadwal.mapel, 'nama_mapel', None))} • {_text(getattr(jadwal.kelas, 'nama_kelas', None))}",
        "tingkat": _tingkat_name(getattr(jadwal.kelas, "tingkat", None)),
        "kelas": _text(getattr(jadwal.kelas, "nama_kelas", None)),
        "mata_pelajaran": _text(getattr(jadwal.mapel, "nama_mapel", None)),
        "hari_jadwal": f"{_text(jadwal.hari)}, {_time(jadwal.jam_mulai)} - {_time(jadwal.jam_selesai)}",
        "status": _status(getattr(jadwal, "status", None)),
    }


def _master_payload():
    selesai_values = ["selesai", "arsip", "diarsipkan", "nonaktif", "tidak aktif"]

    kelas_aktif = Kelas.query.filter(
        func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))) == "aktif"
    ).order_by(Kelas.tahun_ajaran.desc(), Kelas.nama_kelas.asc()).all()
    kelas_riwayat = Kelas.query.filter(
        func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))).in_(selesai_values)
    ).order_by(Kelas.tahun_ajaran.desc(), Kelas.nama_kelas.asc()).all()

    aktif_kelas_ids = [k.id_kelas for k in kelas_aktif]
    riwayat_kelas_ids = [k.id_kelas for k in kelas_riwayat]

    tingkat_aktif_ids = sorted({k.id_tingkat for k in kelas_aktif if k.id_tingkat is not None})
    tingkat_riwayat_ids = sorted({k.id_tingkat for k in kelas_riwayat if k.id_tingkat is not None})
    tingkat_aktif = Tingkat.query.filter(Tingkat.id_tingkat.in_(tingkat_aktif_ids)).all() if tingkat_aktif_ids else []
    tingkat_riwayat = Tingkat.query.filter(Tingkat.id_tingkat.in_(tingkat_riwayat_ids)).all() if tingkat_riwayat_ids else []

    guru_aktif = [g for g in Guru.query.order_by(Guru.nama_guru.asc()).all() if _status(getattr(g, "status", None)) == "aktif"]

    murid_aktif_rows = (
        db.session.query(Murid, MuridTingkat, Kelas, Tingkat)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .join(Kelas, Kelas.id_kelas == MuridTingkat.id_kelas)
        .join(Tingkat, Tingkat.id_tingkat == MuridTingkat.id_tingkat)
        .filter(MuridTingkat.status == "aktif")
        .filter(func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))) == "aktif")
        .order_by(Tingkat.pangkat.asc(), Kelas.nama_kelas.asc(), Murid.nama_murid.asc())
        .all()
    )
    murid_riwayat_rows = (
        db.session.query(Murid, MuridTingkat, Kelas, Tingkat)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .outerjoin(Kelas, Kelas.id_kelas == MuridTingkat.id_kelas)
        .join(Tingkat, Tingkat.id_tingkat == MuridTingkat.id_tingkat)
        .filter(MuridTingkat.status != "aktif")
        .order_by(MuridTingkat.tahun_ajaran.desc(), Murid.nama_murid.asc())
        .all()
    )
    active_student_ids = {m.id_murid for m, _mt, _k, _t in murid_aktif_rows}

    orang_tua_aktif = [
        o for o in OrangTua.query.order_by(OrangTua.nama_ortu.asc()).all()
        if o.id_murid in active_student_ids and _user_status(o.id_user) == "aktif"
    ]

    active_mapel_query = (
        db.session.query(MataPelajaran)
        .join(kelas_mapel, kelas_mapel.c.id_mapel == MataPelajaran.id_mapel)
        .join(Kelas, Kelas.id_kelas == kelas_mapel.c.id_kelas)
        .filter(func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))) == "aktif")
        .distinct()
        .order_by(MataPelajaran.nama_mapel.asc())
    )
    history_mapel_query = (
        db.session.query(MataPelajaran)
        .join(kelas_mapel, kelas_mapel.c.id_mapel == MataPelajaran.id_mapel)
        .join(Kelas, Kelas.id_kelas == kelas_mapel.c.id_kelas)
        .filter(func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))).in_(selesai_values))
        .distinct()
        .order_by(MataPelajaran.nama_mapel.asc())
    )
    mapel_aktif = active_mapel_query.all()
    mapel_riwayat = history_mapel_query.all()

    jadwal_aktif = Jadwal.query.join(Kelas).filter(
        func.lower(func.trim(func.coalesce(Jadwal.status, "aktif"))) == "aktif",
        func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))) == "aktif",
    ).order_by(Jadwal.hari.asc(), Jadwal.jam_mulai.asc()).all()
    jadwal_riwayat = Jadwal.query.join(Kelas).filter(
        or_(
            func.lower(func.trim(func.coalesce(Jadwal.status, "aktif"))).in_(selesai_values),
            func.lower(func.trim(func.coalesce(Kelas.status, "aktif"))).in_(selesai_values),
        )
    ).order_by(Kelas.tahun_ajaran.desc(), Jadwal.hari.asc(), Jadwal.jam_mulai.asc()).all()

    def tingkat_rows(items, kelas_items, badge):
        rows = []
        for t in items:
            jumlah = sum(1 for k in kelas_items if k.id_tingkat == t.id_tingkat)
            rows.append({
                "id": t.id_tingkat,
                "nama": _tingkat_name(t),
                "jumlah_kelas": jumlah,
                "status": badge,
            })
        return rows

    def mapel_rows(items, status_label, class_ids):
        rows = []
        for m in items:
            class_names = (
                db.session.query(Kelas.nama_kelas)
                .join(kelas_mapel, kelas_mapel.c.id_kelas == Kelas.id_kelas)
                .filter(kelas_mapel.c.id_mapel == m.id_mapel)
                .filter(Kelas.id_kelas.in_(class_ids))
                .order_by(Kelas.nama_kelas.asc())
                .all()
            ) if class_ids else []
            tingkat = Tingkat.query.get(m.id_tingkat)
            rows.append({
                "id": m.id_mapel,
                "nama": m.nama_mapel,
                "tingkat": _tingkat_name(tingkat),
                "kelas": ", ".join(row[0] for row in class_names) or "-",
                "status": status_label,
            })
        return rows

    active_details = {
        "tingkat": tingkat_rows(tingkat_aktif, kelas_aktif, "aktif"),
        "kelas": [_kelas_payload(k) for k in kelas_aktif],
        "guru": [
            {
                "id": g.id_guru,
                "nama": g.nama_guru,
                "nip": g.nip,
                "jumlah_jadwal": JadwalGuru.query.join(Jadwal).filter(
                    JadwalGuru.id_guru == g.id_guru,
                    func.lower(func.trim(func.coalesce(Jadwal.status, "aktif"))) == "aktif",
                ).count(),
                "status": _status(getattr(g, "status", None)),
            }
            for g in guru_aktif
        ],
        "murid": [
            {
                "id": m.id_murid,
                "nama": m.nama_murid,
                "nis": m.nis,
                "tingkat": _tingkat_name(t),
                "kelas": k.nama_kelas,
                "tahun_ajaran": mt.tahun_ajaran,
                "status": _status(mt.status),
            }
            for m, mt, k, t in murid_aktif_rows
        ],
        "orang_tua": [
            {
                "id": o.id_ortu,
                "nama": o.nama_ortu,
                "no_hp": _text(o.no_hp),
                "nama_murid": _text(getattr(o.murid, "nama_murid", None)),
                "status": _user_status(o.id_user),
            }
            for o in orang_tua_aktif
        ],
        "mata_pelajaran": mapel_rows(mapel_aktif, "aktif", aktif_kelas_ids),
        "jadwal": [_jadwal_payload(j) for j in jadwal_aktif],
    }

    history_details = {
        "tingkat": tingkat_rows(tingkat_riwayat, kelas_riwayat, "selesai"),
        "kelas": [_kelas_payload(k) for k in kelas_riwayat],
        "murid": [
            {
                "id": m.id_murid,
                "nama": m.nama_murid,
                "nis": m.nis,
                "tingkat": _tingkat_name(t),
                "kelas": _text(getattr(k, "nama_kelas", None)),
                "tahun_ajaran": mt.tahun_ajaran,
                "status": _status(mt.status, "selesai"),
            }
            for m, mt, k, t in murid_riwayat_rows
        ],
        "mata_pelajaran": mapel_rows(mapel_riwayat, "selesai", riwayat_kelas_ids),
        "jadwal": [_jadwal_payload(j) for j in jadwal_riwayat],
    }

    return {
        "active": {
            "summary": {key: len(value) for key, value in active_details.items()},
            "details": active_details,
        },
        "history": {
            "summary": {key: len(value) for key, value in history_details.items()},
            "details": history_details,
        },
    }


def _date_range(range_key):
    today = datetime.now().date()
    key = (range_key or "day").strip().lower()
    semester = None
    tahun_ajaran = None

    if key == "week":
        return today - timedelta(days=6), today, "1 Minggu", semester, tahun_ajaran
    if key == "month":
        return today - timedelta(days=29), today, "1 Bulan", semester, tahun_ajaran

    if key in ("ganjil", "genap"):
        period = PeriodeAkademik.query.filter_by(semester=key).order_by(
            PeriodeAkademik.tanggal_mulai.desc(), PeriodeAkademik.id_periode.desc()
        ).first()
        if period:
            return period.tanggal_mulai, period.tanggal_selesai, f"Semester {key.title()} • {period.tahun_ajaran}", key, period.tahun_ajaran
        return today, today, f"Semester {key.title()}", key, None

    if key == "year":
        active = PeriodeAkademik.aktif() or PeriodeAkademik.query.order_by(
            PeriodeAkademik.tanggal_mulai.desc(), PeriodeAkademik.id_periode.desc()
        ).first()
        if active:
            periods = PeriodeAkademik.query.filter_by(tahun_ajaran=active.tahun_ajaran).all()
            starts = [p.tanggal_mulai for p in periods if p.tanggal_mulai]
            ends = [p.tanggal_selesai for p in periods if p.tanggal_selesai]
            if starts and ends:
                return min(starts), max(ends), f"1 Tahun Ajaran • {active.tahun_ajaran}", None, active.tahun_ajaran
        return today - timedelta(days=364), today, "1 Tahun Ajaran", None, None

    return today, today, "1 Hari", semester, tahun_ajaran


def _count_status(rows, getter):
    result = {"hadir": 0, "izin": 0, "sakit": 0, "alpa": 0, "lainnya": 0}
    for row in rows:
        value = _status(getter(row), "lainnya")
        if value in ("hadir", "selesai", "masuk"):
            result["hadir"] += 1
        elif value in ("izin", "ijin"):
            result["izin"] += 1
        elif value == "sakit":
            result["sakit"] += 1
        elif value in ("alpa", "alpha", "tidak hadir"):
            result["alpa"] += 1
        else:
            result["lainnya"] += 1
    return result


def _chart_payload(counts, source):
    total = sum(counts.values())
    hadir = counts.get("hadir", 0)
    return {
        "total": total,
        "hadir": hadir,
        "izin": counts.get("izin", 0),
        "sakit": counts.get("sakit", 0),
        "alpa": counts.get("alpa", 0),
        "lainnya": counts.get("lainnya", 0),
        "persentase_hadir": round((hadir / total * 100), 1) if total else 0.0,
        "source": source,
    }


@master_data_bp.route("/admin/master-data", methods=["GET"])
@jwt_required()
def get_master_data():
    return jsonify(_master_payload()), 200


@master_data_bp.route("/admin/master-data/attendance", methods=["GET"])
@jwt_required()
def get_master_data_attendance():
    range_key = request.args.get("range", "day")
    start, end, label, semester, tahun_ajaran = _date_range(range_key)

    guru_rows = KehadiranGuru.query.filter(
        KehadiranGuru.tanggal >= start,
        KehadiranGuru.tanggal <= end,
    ).all()
    guru_counts = _count_status(guru_rows, lambda row: row.status)

    murid_query = KehadiranMurid.query.filter(
        KehadiranMurid.tanggal >= start,
        KehadiranMurid.tanggal <= end,
    )
    if semester:
        murid_query = murid_query.filter(KehadiranMurid.semester == semester)
    if tahun_ajaran:
        murid_query = murid_query.filter(KehadiranMurid.tahun_ajaran == tahun_ajaran)
    murid_rows = murid_query.all()
    murid_counts = _count_status(murid_rows, lambda row: row.status)

    monitor_rows = LaporanMonitoring.query.filter(
        LaporanMonitoring.tanggal >= start,
        LaporanMonitoring.tanggal <= end,
    ).all()
    monitor_count = len(monitor_rows)
    if not guru_rows and monitor_rows:
        guru_counts = _count_status(monitor_rows, lambda row: row.status)
        guru_source = "Laporan monitoring guru"
    else:
        guru_source = "Kehadiran guru per jadwal (tersinkron monitoring)"

    laporan_rows = (
        db.session.query(LaporanMengajar)
        .join(LaporanMonitoring, LaporanMonitoring.id_monitor == LaporanMengajar.id_monitor)
        .filter(LaporanMonitoring.tanggal >= start, LaporanMonitoring.tanggal <= end)
        .all()
    )
    laporan_hadir = sum(int(getattr(row, "jumlah_hadir", 0) or 0) for row in laporan_rows)
    laporan_tidak_hadir = sum(int(getattr(row, "jumlah_tidak_hadir", 0) or 0) for row in laporan_rows)

    if not murid_rows and (laporan_hadir + laporan_tidak_hadir) > 0:
        murid_counts["hadir"] = laporan_hadir
        murid_counts["alpa"] = laporan_tidak_hadir
        murid_source = "Laporan mengajar (fallback karena input kehadiran murid belum tersedia)"
    else:
        murid_source = "Input kehadiran murid"

    return jsonify({
        "range": range_key,
        "label": label,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "guru": _chart_payload(guru_counts, guru_source),
        "murid": _chart_payload(murid_counts, murid_source),
        "sources": {
            "monitoring": monitor_count,
            "laporan_mengajar": len(laporan_rows),
            "input_kehadiran_murid": len(murid_rows),
            "jumlah_hadir_laporan": laporan_hadir,
            "jumlah_tidak_hadir_laporan": laporan_tidak_hadir,
        },
    }), 200
