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
    ML_MODEL_PATH = os.getenv(
        "ML_MODEL_PATH",
        str(PROJECT_ROOT / "ml_model" / "artifacts" / "phishguard_url_model.joblib"),
    )


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret-key-longer-than-thirty-two-bytes"
