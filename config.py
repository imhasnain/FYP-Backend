# ============================================================
# config.py — Central configuration for the FYP backend
# All settings are read from environment variables with
# sensible defaults so the app runs out-of-the-box.
# ============================================================

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide settings loaded from environment variables.
    Override any value by setting the corresponding env var or
    placing it in a .env file in the project root.
    """

    # ── Database (SQL Server) ──────────────────────────────
    DB_SERVER: str = "localhost"          # SQL Server host / instance
    DB_NAME: str = "VirtualClinicDB"      # Database name
    DB_USER: str = ""                     # Leave empty for Windows Auth
    DB_PASSWORD: str = ""                 # Leave empty for Windows Auth
    DB_TRUSTED_CONNECTION: bool = True    # True = Windows Authentication

    # ── JWT Authentication ─────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_LONG_RANDOM_STRING"
    ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_MINUTES: int = 480       # 8 hours

    # ── Bluetooth BLE Settings ─────────────────────────────
    BLE_SCAN_TIMEOUT: int = 15            # Seconds to scan for BP device
    BP_GATT_UUID: str = "00002a35-0000-1000-8000-00805f9b34fb"

    # ── EEG Streaming Settings ─────────────────────────────
    EEG_BATCH_SIZE: int = 50             # Insert every 50 readings at once

    # ── Facial Emotion Detection ───────────────────────────
    EMOTION_INTERVAL_SECONDS: int = 5    # Capture emotion every N seconds
    EMOTION_IMAGES_DIR: str = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "emotion_images"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton instance — import this everywhere
settings = Settings()
