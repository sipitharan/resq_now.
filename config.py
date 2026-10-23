import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE, override=True)


class Config:
    SECRET_KEY = os.getenv("RESQNOW_SECRET_KEY", "dev-only-change-this-secret")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///resqnow.db")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = bool(os.getenv("VERCEL"))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    UPLOAD_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
    RATELIMIT_DEFAULT = "200/day;60/hour;10/minute"
    RATELIMIT_STORAGE_URI = "memory://"
    REALTIME_PROVIDER = os.getenv("REALTIME_PROVIDER", "pusher" if os.getenv("VERCEL") else "socketio").lower()
    PUSHER_APP_ID = os.getenv("PUSHER_APP_ID")
    PUSHER_KEY = os.getenv("PUSHER_KEY")
    PUSHER_SECRET = os.getenv("PUSHER_SECRET")
    PUSHER_CLUSTER = os.getenv("PUSHER_CLUSTER")
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "driver-documents")

    if os.getenv("VERCEL"):
        required = ("DATABASE_URL", "RESQNOW_SECRET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Vercel configuration is missing: {', '.join(missing)}")
        if not DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Vercel deployments require a persistent PostgreSQL DATABASE_URL")
        if REALTIME_PROVIDER != "pusher":
            raise RuntimeError("Vercel deployments require REALTIME_PROVIDER=pusher")
