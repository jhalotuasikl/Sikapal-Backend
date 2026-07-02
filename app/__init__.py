from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db, jwt


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    db.init_app(app)
    jwt.init_app(app)

    from .routes import register_routes
    register_routes(app)

    with app.app_context():
        try:
            from .utils.auto_migrate import ensure_schema
            ensure_schema(db)
        except Exception:
            pass

    return app