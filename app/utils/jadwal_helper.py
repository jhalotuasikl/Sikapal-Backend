from app.extensions import db
from app.models.jadwal import Jadwal
from app.models.jadwal_murid import jadwal_murid
from app.models.murid import Murid
from app.models.kelas import Kelas
from app.models.murid_tingkat import MuridTingkat


def sinkron_jadwal_murid(id_murid, id_kelas, daftar_id_mapel):
    """
    Sinkronkan relasi murid ke tabel jadwal_murid
    berdasarkan kelas dan daftar mapel yang dimiliki murid.
    """

    if not id_murid or not id_kelas or not daftar_id_mapel:
        return

    kelas = Kelas.query.get(id_kelas)
    if kelas and str(getattr(kelas, "status", "aktif") or "aktif").strip().lower() != "aktif":
        return

    # Ambil semua jadwal aktif sesuai kelas + mapel
    daftar_jadwal = Jadwal.query.filter(
        Jadwal.id_kelas == id_kelas,
        Jadwal.id_mapel.in_(daftar_id_mapel),
        Jadwal.status == "aktif",
    ).all()

    # Jadwal yang seharusnya dimiliki murid
    target_jadwal_ids = {j.id_jadwal for j in daftar_jadwal}

    # Jadwal yang sekarang sudah dimiliki murid
    existing_rows = db.session.execute(
        db.select(jadwal_murid.c.id_jadwal).where(
            jadwal_murid.c.id_murid == id_murid
        )
    ).all()

    existing_jadwal_ids = {row[0] for row in existing_rows}

    # =========================
    # Tambah relasi yang belum ada
    # =========================
    jadwal_to_add = target_jadwal_ids - existing_jadwal_ids
    for id_jadwal in jadwal_to_add:
        db.session.execute(
            jadwal_murid.insert().values(
                id_jadwal=id_jadwal,
                id_murid=id_murid
            )
        )

    # =========================
    # Hapus relasi yang tidak sesuai lagi
    # hanya untuk jadwal dalam kelas yang sama
    # =========================
    jadwal_kelas_ini = Jadwal.query.filter_by(id_kelas=id_kelas, status="aktif").all()
    jadwal_kelas_ids = {j.id_jadwal for j in jadwal_kelas_ini}

    jadwal_to_remove = (existing_jadwal_ids & jadwal_kelas_ids) - target_jadwal_ids
    for id_jadwal in jadwal_to_remove:
        db.session.execute(
            jadwal_murid.delete().where(
                jadwal_murid.c.id_jadwal == id_jadwal,
                jadwal_murid.c.id_murid == id_murid
            )
        )


def tambah_semua_murid_ke_jadwal(id_jadwal, id_kelas):
    """
    Saat jadwal baru dibuat, masukkan semua murid di kelas tsb
    ke jadwal_murid.
    """

    if not id_jadwal or not id_kelas:
        return

    jadwal = Jadwal.query.get(id_jadwal)
    kelas = Kelas.query.get(id_kelas)
    if (not jadwal or str(getattr(jadwal, "status", "aktif") or "aktif").strip().lower() != "aktif"
            or (kelas and str(getattr(kelas, "status", "aktif") or "aktif").strip().lower() != "aktif")):
        return

    daftar_murid = (
        db.session.query(Murid)
        .join(MuridTingkat, MuridTingkat.id_murid == Murid.id_murid)
        .filter(
            MuridTingkat.id_kelas == id_kelas,
            MuridTingkat.status == "aktif",
        )
        .all()
    )

    if not daftar_murid:
        daftar_murid = Murid.query.filter_by(id_kelas=id_kelas).all()

    for murid in daftar_murid:
        cek = db.session.execute(
            db.select(jadwal_murid).where(
                jadwal_murid.c.id_jadwal == id_jadwal,
                jadwal_murid.c.id_murid == murid.id_murid
            )
        ).first()

        if not cek:
            db.session.execute(
                jadwal_murid.insert().values(
                    id_jadwal=id_jadwal,
                    id_murid=murid.id_murid
                )
            )


def hapus_relasi_jadwal_murid_di_kelas(id_murid, id_kelas):
    """
    Opsional: hapus semua relasi jadwal_murid seorang murid
    pada kelas tertentu.
    Cocok dipakai saat murid pindah kelas.
    """
    if not id_murid or not id_kelas:
        return

    jadwal_kelas = Jadwal.query.filter_by(id_kelas=id_kelas).all()
    jadwal_ids = [j.id_jadwal for j in jadwal_kelas]

    if not jadwal_ids:
        return

    db.session.execute(
        jadwal_murid.delete().where(
            jadwal_murid.c.id_murid == id_murid,
            jadwal_murid.c.id_jadwal.in_(jadwal_ids)
        )
    )