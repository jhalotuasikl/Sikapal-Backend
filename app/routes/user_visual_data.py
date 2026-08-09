from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.role import Role
from app.models.guru import Guru
from app.models.murid import Murid
from app.models.orang_tua_models import OrangTua
from app.models.kelas import Kelas
from app.models.tingkat import Tingkat
from app.models.mata_pelajaran import MataPelajaran
from app.models.jadwal import Jadwal
from app.models.jadwal_guru import JadwalGuru
from app.models.jadwal_murid import jadwal_murid
from app.models.kehadiran_murid import KehadiranMurid
from app.models.kehadiran_guru import KehadiranGuru
from app.models.nilai import Nilai
from app.models.monitoring import LaporanMonitoring
from app.models.mengajar import LaporanMengajar
from app.models.kuisoner import Kuisoner
from app.models.jawaban_kuisoner import JawabanKuisoner
from app.models.detail_jawaban_kuisoner import DetailJawabanKuisoner


user_visual_data_bp = Blueprint("user_visual_data", __name__)


def _text(value, default="-"):
    text = str(value if value is not None else "").strip()
    return text if text and text.lower() not in {"none", "null"} else default


def _role(user):
    role = Role.query.get(user.id_role) if user else None
    return _text(getattr(role, "nama_role", None), "").lower().replace(" ", "_")


def _status_counts(rows, getter):
    result = {"hadir": 0, "izin": 0, "sakit": 0, "alpa": 0}
    for row in rows:
        value = _text(getter(row), "").lower().replace("_", " ")
        if value in {"hadir", "masuk", "selesai"}:
            result["hadir"] += 1
        elif value in {"izin", "ijin"}:
            result["izin"] += 1
        elif value == "sakit":
            result["sakit"] += 1
        elif value in {"alpa", "alpha", "tidak hadir"}:
            result["alpa"] += 1
    total = sum(result.values())
    result["total"] = total
    for key in ("hadir", "izin", "sakit", "alpa"):
        result[f"persentase_{key}"] = round(result[key] / total * 100, 1) if total else 0.0
    return result


def _jadwal_payload(j):
    return {
        "id": j.id_jadwal,
        "nama": _text(getattr(j.mapel, "nama_mapel", None)),
        "mapel": _text(getattr(j.mapel, "nama_mapel", None)),
        "kelas": _text(getattr(j.kelas, "nama_kelas", None)),
        "tingkat": _text(getattr(getattr(j.kelas, "tingkat", None), "pangkat", None)),
        "hari": _text(j.hari),
        "jam_mulai": j.jam_mulai.strftime("%H:%M") if j.jam_mulai else "-",
        "jam_selesai": j.jam_selesai.strftime("%H:%M") if j.jam_selesai else "-",
        "status": _text(getattr(j, "status", None), "aktif"),
    }


def _student_data(murid, requested_role="murid", parent=None):
    kelas = Kelas.query.get(murid.id_kelas) if murid and murid.id_kelas else None
    tingkat = Tingkat.query.get(kelas.id_tingkat) if kelas and kelas.id_tingkat else None

    schedule_ids = {
        row[0]
        for row in db.session.query(jadwal_murid.c.id_jadwal)
        .filter(jadwal_murid.c.id_murid == murid.id_murid)
        .all()
    }
    if kelas:
        schedule_ids.update(
            row[0]
            for row in db.session.query(Jadwal.id_jadwal)
            .filter(Jadwal.id_kelas == kelas.id_kelas)
            .all()
        )
    jadwal_rows = Jadwal.query.filter(Jadwal.id_jadwal.in_(schedule_ids)).all() if schedule_ids else []
    jadwal_rows.sort(key=lambda j: (_text(j.hari), j.jam_mulai or datetime.min.time()))

    mapel_by_id = {}
    guru_by_id = {}
    for j in jadwal_rows:
        if j.mapel:
            mapel_by_id[j.mapel.id_mapel] = j.mapel
        for jg in JadwalGuru.query.filter_by(id_jadwal=j.id_jadwal).all():
            if jg.guru:
                guru_by_id[jg.guru.id_guru] = jg.guru

    attendance_rows = KehadiranMurid.query.filter_by(id_murid=murid.id_murid).order_by(
        KehadiranMurid.tanggal.desc(), KehadiranMurid.pertemuan.desc()
    ).all()
    nilai_rows = Nilai.query.filter_by(id_murid=murid.id_murid).order_by(Nilai.id_nilai.desc()).all()
    parents = OrangTua.query.filter_by(id_murid=murid.id_murid).order_by(OrangTua.nama_ortu.asc()).all()
    questionnaire_rows = (
        Kuisoner.query.filter(
            Kuisoner.id_jadwal.in_(schedule_ids),
            Kuisoner.status.in_(["dibuka", "ditutup", "selesai"]),
        ).all()
        if schedule_ids else []
    )
    questionnaire_ids = [q.id_kuisoner for q in questionnaire_rows]
    answered_rows = (
        JawabanKuisoner.query.filter(
            JawabanKuisoner.id_murid == murid.id_murid,
            JawabanKuisoner.id_kuisoner.in_(questionnaire_ids),
        ).all()
        if questionnaire_ids else []
    )
    answered_ids = [row.id_jawaban for row in answered_rows]
    student_quiz_avg = float(
        db.session.query(func.avg(DetailJawabanKuisoner.skor))
        .filter(DetailJawabanKuisoner.id_jawaban.in_(answered_ids))
        .scalar() or 0
    ) if answered_ids else 0.0

    attendance = _status_counts(attendance_rows, lambda row: row.status)
    week_start = datetime.now().date() - timedelta(days=6)
    attendance_week = _status_counts(
        [row for row in attendance_rows if row.tanggal and row.tanggal >= week_start],
        lambda row: row.status,
    )
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for n in nilai_rows:
        huruf = _text(getattr(n, "nilai_huruf", None), "").upper()
        if huruf in grade_counts:
            grade_counts[huruf] += 1

    details = {
        "tingkat": [{"nama": f"Tingkat {_text(getattr(tingkat, 'pangkat', None))}", "status": "aktif"}] if tingkat else [],
        "kelas": [{"nama": _text(getattr(kelas, "nama_kelas", None)), "tahun_ajaran": _text(getattr(kelas, "tahun_ajaran", None)), "status": _text(getattr(kelas, "status", None), "aktif")}] if kelas else [],
        "mata_pelajaran": [{"id": m.id_mapel, "nama": m.nama_mapel} for m in sorted(mapel_by_id.values(), key=lambda x: x.nama_mapel)],
        "jadwal": [_jadwal_payload(j) for j in jadwal_rows],
        "guru": [{"id": g.id_guru, "nama": g.nama_guru, "nip": g.nip} for g in sorted(guru_by_id.values(), key=lambda x: x.nama_guru)],
        "orang_tua": [{"id": o.id_ortu, "nama": o.nama_ortu, "no_hp": _text(o.no_hp)} for o in parents],
        "kehadiran": [{
            "id": r.id_kehadiran,
            "tanggal": r.tanggal.isoformat() if r.tanggal else None,
            "status": _text(r.status),
            "pertemuan": r.pertemuan,
            "jadwal": _jadwal_payload(r.jadwal) if r.jadwal else {},
        } for r in attendance_rows],
        "nilai": [{
            "id": n.id_nilai,
            "nilai": float(n.nilai_angka or 0),
            "huruf": _text(n.nilai_huruf),
            "semester": _text(n.semester),
            "tahun_ajaran": _text(n.tahun_ajaran),
            "jadwal": _jadwal_payload(n.jadwal) if n.jadwal else {},
        } for n in nilai_rows],
    }
    summary = {key: len(value) for key, value in details.items()}
    identity = {
        "role": requested_role,
        "id_murid": murid.id_murid,
        "nama": parent.nama_ortu if parent else murid.nama_murid,
        "nama_murid": murid.nama_murid,
        "nis": murid.nis,
        "id_orang_tua": parent.id_ortu if parent else None,
        "nomor_telepon": parent.no_hp if parent else None,
    }
    return {
        "role": requested_role,
        "identity": identity,
        "summary": summary,
        "details": details,
        "attendance": attendance,
        "attendance_week": attendance_week,
        "grades": {"total": len(nilai_rows), **grade_counts},
        "questionnaire": {
            "total": len(questionnaire_rows),
            "diisi": len(answered_rows),
            "belum_diisi": max(0, len(questionnaire_rows) - len(answered_rows)),
            "partisipasi": round(len(answered_rows) / len(questionnaire_rows) * 100, 1) if questionnaire_rows else 0.0,
            "score_rata_rata": round(student_quiz_avg, 2),
        },
        "latest_grades": details["nilai"][:8],
        "latest_attendance": [
            row for row in details["kehadiran"]
            if row.get("tanggal") and datetime.fromisoformat(row["tanggal"]).date() >= week_start
        ],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _teacher_data(guru):
    assignments = JadwalGuru.query.filter_by(id_guru=guru.id_guru).all()
    schedule_ids = sorted({row.id_jadwal for row in assignments if row.id_jadwal})
    schedules = Jadwal.query.filter(Jadwal.id_jadwal.in_(schedule_ids)).all() if schedule_ids else []
    schedule_by_id = {j.id_jadwal: j for j in schedules}

    mapel_by_id, kelas_by_id, tingkat_by_id = {}, {}, {}
    for j in schedules:
        if j.mapel:
            mapel_by_id[j.mapel.id_mapel] = j.mapel
        if j.kelas:
            kelas_by_id[j.kelas.id_kelas] = j.kelas
            if j.kelas.tingkat:
                tingkat_by_id[j.kelas.tingkat.id_tingkat] = j.kelas.tingkat

    student_ids = set()
    if schedule_ids:
        student_ids.update(
            row[0]
            for row in db.session.query(jadwal_murid.c.id_murid)
            .filter(jadwal_murid.c.id_jadwal.in_(schedule_ids))
            .all()
        )
    if not student_ids and kelas_by_id:
        student_ids.update(
            row[0]
            for row in db.session.query(Murid.id_murid)
            .filter(Murid.id_kelas.in_(list(kelas_by_id.keys())))
            .all()
        )
    students = Murid.query.filter(Murid.id_murid.in_(student_ids)).order_by(Murid.nama_murid.asc()).all() if student_ids else []

    attendance_rows = KehadiranGuru.query.filter_by(id_guru=guru.id_guru).order_by(KehadiranGuru.tanggal.desc()).all()
    monitoring_rows = LaporanMonitoring.query.filter(LaporanMonitoring.id_jadwal.in_(schedule_ids)).order_by(LaporanMonitoring.tanggal.desc()).all() if schedule_ids else []
    monitor_ids = [m.id_monitor for m in monitoring_rows]
    report_rows = LaporanMengajar.query.filter(LaporanMengajar.id_monitor.in_(monitor_ids)).order_by(LaporanMengajar.waktu_input.desc()).all() if monitor_ids else []
    questionnaire_rows = Kuisoner.query.filter(Kuisoner.id_jadwal.in_(schedule_ids)).order_by(Kuisoner.id_kuisoner.desc()).all() if schedule_ids else []
    questionnaire_ids = [q.id_kuisoner for q in questionnaire_rows]
    q_avg = 0.0
    if questionnaire_ids:
        q_avg = float(
            db.session.query(func.avg(DetailJawabanKuisoner.skor))
            .join(JawabanKuisoner, JawabanKuisoner.id_jawaban == DetailJawabanKuisoner.id_jawaban)
            .filter(JawabanKuisoner.id_kuisoner.in_(questionnaire_ids))
            .scalar() or 0
        )

    attendance = _status_counts(attendance_rows, lambda row: row.status)
    week_start = datetime.now().date() - timedelta(days=6)
    attendance_week = _status_counts(
        [row for row in attendance_rows if row.tanggal and row.tanggal >= week_start],
        lambda row: row.status,
    )
    details = {
        "tingkat": [{"id": t.id_tingkat, "nama": f"Tingkat {t.pangkat}"} for t in sorted(tingkat_by_id.values(), key=lambda x: x.pangkat)],
        "kelas": [{"id": k.id_kelas, "nama": k.nama_kelas, "tahun_ajaran": k.tahun_ajaran, "status": _text(k.status, "aktif")} for k in sorted(kelas_by_id.values(), key=lambda x: x.nama_kelas)],
        "mata_pelajaran": [{"id": m.id_mapel, "nama": m.nama_mapel} for m in sorted(mapel_by_id.values(), key=lambda x: x.nama_mapel)],
        "jadwal": [_jadwal_payload(j) for j in schedules],
        "murid": [{"id": m.id_murid, "nama": m.nama_murid, "nis": m.nis} for m in students],
        "monitoring": [{"id": r.id_kehadiran, "tanggal": r.tanggal.isoformat() if r.tanggal else None, "status": _text(r.status), "id_jadwal": r.id_jadwal} for r in attendance_rows],
        "laporan_mengajar": [{
            "id": r.id_laporan,
            "materi": _text(r.materi),
            "catatan": _text(r.catatan),
            "jumlah_hadir": r.jumlah_hadir,
            "jumlah_tidak_hadir": r.jumlah_tidak_hadir,
            "waktu_input": r.waktu_input.isoformat(timespec="minutes") if r.waktu_input else None,
            "tanggal": r.monitoring.tanggal.isoformat() if r.monitoring and r.monitoring.tanggal else None,
            "jadwal": _jadwal_payload(r.monitoring.jadwal) if r.monitoring and r.monitoring.jadwal else {},
        } for r in report_rows],
        "kuisoner": [{
            "id": q.id_kuisoner,
            "status": _text(q.status),
            "semester": _text(q.semester),
            "tahun_ajaran": _text(q.tahun_ajaran),
            "jadwal": _jadwal_payload(schedule_by_id[q.id_jadwal]) if q.id_jadwal in schedule_by_id else {},
        } for q in questionnaire_rows],
    }
    summary = {key: len(value) for key, value in details.items()}

    today = datetime.now().date()
    report_periods = {
        "hari": sum(1 for r in report_rows if r.waktu_input and r.waktu_input.date() == today),
        "minggu": sum(1 for r in report_rows if r.waktu_input and r.waktu_input.date() >= today - timedelta(days=6)),
        "bulan": sum(1 for r in report_rows if r.waktu_input and r.waktu_input.date() >= today - timedelta(days=29)),
        "total": len(report_rows),
    }

    return {
        "role": "guru",
        "identity": {"role": "guru", "id_guru": guru.id_guru, "nama": guru.nama_guru, "nip": guru.nip},
        "summary": summary,
        "details": details,
        "attendance": attendance,
        "attendance_week": attendance_week,
        "questionnaire": {"total": len(questionnaire_rows), "score_rata_rata": round(q_avg, 2)},
        "reports": report_periods,
        "latest_reports": [
            row for row in details["laporan_mengajar"]
            if row.get("waktu_input") and datetime.fromisoformat(row["waktu_input"]).date() >= today - timedelta(days=6)
        ],
        "latest_attendance": [
            row for row in details["monitoring"]
            if row.get("tanggal") and datetime.fromisoformat(row["tanggal"]).date() >= today - timedelta(days=6)
        ],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@user_visual_data_bp.route("/user/visual-data", methods=["GET"])
@jwt_required()
def get_user_visual_data():
    user = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"message": "Akun tidak ditemukan. Silakan login kembali."}), 404

    role_name = _role(user)
    if role_name == "guru":
        guru = Guru.query.filter_by(id_user=user.id_user).first()
        if not guru:
            return jsonify({"message": "Data guru tidak ditemukan."}), 404
        return jsonify(_teacher_data(guru)), 200

    if role_name == "murid":
        murid = Murid.query.filter_by(id_user=user.id_user).first()
        if not murid:
            return jsonify({"message": "Data murid tidak ditemukan."}), 404
        return jsonify(_student_data(murid, "murid")), 200

    if role_name == "orang_tua":
        parent = OrangTua.query.filter_by(id_user=user.id_user).first()
        if not parent:
            return jsonify({"message": "Data orang tua tidak ditemukan."}), 404
        murid = Murid.query.get(parent.id_murid)
        if not murid:
            return jsonify({"message": "Data anak tidak ditemukan."}), 404
        return jsonify(_student_data(murid, "orang_tua", parent=parent)), 200

    return jsonify({"message": "Visual data akun hanya tersedia untuk guru, murid, dan orang tua."}), 403
