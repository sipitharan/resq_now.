from flask import Flask, jsonify
from flask_login import LoginManager

from config import Config
from models import db, User
from extensions import initialize_realtime, limiter, socketio

login_manager = LoginManager()


def _ensure_schema():
    """Add fields required by newer releases to an existing SQLite database."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    additions = {
        "users": {
            "mobile_verified": "BOOLEAN NOT NULL DEFAULT 0",
            "verification_timestamp": "DATETIME",
            "updated_at": "DATETIME",
        },
        "drivers": {
            "phone": "VARCHAR(30)",
            "phone_verified": "BOOLEAN NOT NULL DEFAULT 0",
            "verified_at": "DATETIME",
            "ambulance_registration_number": "VARCHAR(40)",
            "verification_score": "INTEGER",
            "photo_path": "VARCHAR(255)",
            "ai_result": "VARCHAR(30)",
            "ai_confidence": "INTEGER",
            "ai_risk_score": "INTEGER",
            "ocr_result": "VARCHAR(80)",
            "ocr_match": "VARCHAR(20)",
            "last_gps_at": "DATETIME",
            "gps_status": "VARCHAR(10) NOT NULL DEFAULT 'LOST'",
            "reliability_score": "FLOAT NOT NULL DEFAULT 50",
            "acceptance_rate": "FLOAT NOT NULL DEFAULT 0",
            "cancellation_rate": "FLOAT NOT NULL DEFAULT 0",
            "completed_trips": "INTEGER NOT NULL DEFAULT 0",
            "total_requests": "INTEGER NOT NULL DEFAULT 0",
            "average_response_seconds": "FLOAT NOT NULL DEFAULT 0",
            "gps_anomaly_count": "INTEGER NOT NULL DEFAULT 0",
        },
        "ambulances": {"capabilities": "TEXT"},
        "bookings": {
            "smart_dispatch_score": "FLOAT",
            "distance_km": "FLOAT",
            "eta_minutes": "INTEGER",
            "requested_at": "DATETIME",
            "notified_at": "DATETIME",
            "accepted_at": "DATETIME",
            "en_route_at": "DATETIME",
            "arrived_at": "DATETIME",
            "completed_at": "DATETIME",
            "rejected_at": "DATETIME",
            "escalation_count": "INTEGER NOT NULL DEFAULT 0",
            "priority": "VARCHAR(12) NOT NULL DEFAULT 'MEDIUM'",
            "emergency_category": "VARCHAR(80)",
            "hospital_id": "INTEGER",
        },
        "driver_locations": {"gps_status": "VARCHAR(10) NOT NULL DEFAULT 'LIVE'"},
        "verification_records": {
            "ambulance_proof_path": "VARCHAR(255)",
            "mobile_verified": "BOOLEAN NOT NULL DEFAULT 0",
            "document_status": "VARCHAR(30) NOT NULL DEFAULT 'SUBMITTED'",
            "ai_risk_score": "INTEGER",
            "ai_flags": "TEXT",
            "review_status": "VARCHAR(30) NOT NULL DEFAULT 'PENDING'",
            "ai_result": "VARCHAR(30)",
            "ai_confidence": "INTEGER",
            "ocr_result": "VARCHAR(80)",
            "ocr_match": "VARCHAR(20)",
            "photo_sha256": "VARCHAR(64)",
        },
    }
    with db.engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
            if table == "users" and "updated_at" not in existing:
                connection.execute(text("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL"))
def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    limiter.init_app(app)
    if app.config["REALTIME_PROVIDER"] == "socketio":
        socketio.init_app(app)
    initialize_realtime(app)

    with app.app_context():
        db.create_all()
        _ensure_schema()


    @app.get("/health")
    def health():
        return jsonify(status="ok", service="ResQNow prototype")

    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.api import api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


app = create_app()


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5000, debug=True, allow_unsafe_werkzeug=True)
