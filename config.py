"""config.py — Central configuration for the Virtual Clinic backend."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # ── Database (SQL Server) ──────────────────────────────
    DB_SERVER: str = "localhost"
    DB_NAME: str = "VirtualClinicDB"
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_TRUSTED_CONNECTION: bool = True

    # ── JWT Authentication ─────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_LONG_RANDOM_STRING"
    ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_MINUTES: int = 480

    # ── Withings Health API (OAuth2) ───────────────────────
    WITHINGS_CLIENT_ID: str = ""
    WITHINGS_CLIENT_SECRET: str = ""
    WITHINGS_REDIRECT_URI: str = "http://localhost:8000/withings/callback"

    # ── EEG Streaming ─────────────────────────────────────
    EEG_BATCH_SIZE: int = 50

    # ── Facial Emotion Detection ───────────────────────────
    EMOTION_INTERVAL_SECONDS: int = 5
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    EMOTION_IMAGES_DIR: str = os.path.join(BASE_DIR, "emotion_images")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=False, extra="ignore",
    )


settings = Settings()
