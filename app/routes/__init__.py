from .auth import auth_bp
from .admin_murid import admin_murid_bp
from .admin_promosi import admin_promosi_bp
from .admin_guru import admin_guru_bp
from .kehadiran import kehadiran_bp
from .nilai import nilai_bp
from .pengaduan import pengaduan_bp
from .admin_kelas import admin_kelas_bp, kelas_bp
from .admin_tingkat import admin_tingkat_bp
from .mata_pelajaran import mapel_bp
from .jadwal import jadwal_bp
from .laporan_monitoring import monitoring_bp
from .kelas_mapel import kelas_mapel_bp
from .kehadiran import admin_bp
from .guru import guru_bp
from .murid import murid_bp
from .kuisoner import kuisoner_bp
from .periode_akademik import periode_akademik_bp

def register_routes(app):

    # AUTH
    app.register_blueprint(auth_bp, url_prefix='/api')


    # ADMIN
    app.register_blueprint(admin_murid_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_promosi_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_guru_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_kelas_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_tingkat_bp, url_prefix='/api/admin')
    
    app.register_blueprint(admin_bp, url_prefix='/api')


    # MAPEL
    app.register_blueprint(mapel_bp, url_prefix='/api')
    app.register_blueprint(kelas_bp, url_prefix='/api')
    app.register_blueprint(kelas_mapel_bp, url_prefix="/api")


    # UMUM / GURU
    app.register_blueprint(kehadiran_bp, url_prefix='/api')
    app.register_blueprint(nilai_bp, url_prefix='/api')      # ✅ cukup sekali
    app.register_blueprint(pengaduan_bp, url_prefix="/api")
    app.register_blueprint(jadwal_bp, url_prefix='/api')
    app.register_blueprint(monitoring_bp, url_prefix='/api')
    app.register_blueprint(guru_bp, url_prefix='/api')
    app.register_blueprint(murid_bp, url_prefix="/api")
    app.register_blueprint(kuisoner_bp, url_prefix="/api")
    app.register_blueprint(periode_akademik_bp, url_prefix="/api")
