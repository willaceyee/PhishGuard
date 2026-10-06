import os
from datetime import timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-before-deployment-2026")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/phishguard"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    )
    ML_MODEL_PATH = os.getenv(
        "ML_MODEL_PATH",
        str(PROJECT_ROOT / "ml_model" / "artifacts" / "phishguard_url_model.joblib"),
    )
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")
    MAIL_DELIVERY_ENABLED = os.getenv("MAIL_DELIVERY_ENABLED", "0") == "1"
    MAIL_HOST = os.getenv("MAIL_HOST", "127.0.0.1")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "1025"))
    MAIL_FROM = os.getenv("MAIL_FROM", "simulation@phishguard.test")
    MAX_CAMPAIGN_RECIPIENTS = int(os.getenv("MAX_CAMPAIGN_RECIPIENTS", "25"))
    MAX_EMAILS_PER_HOUR = int(os.getenv("MAX_EMAILS_PER_HOUR", "50"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret-key-longer-than-thirty-two-bytes"
    PUBLIC_BASE_URL = "http://localhost"
    MAIL_DELIVERY_ENABLED = True
    MAX_CAMPAIGN_RECIPIENTS = 5
    MAX_EMAILS_PER_HOUR = 10
