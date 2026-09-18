"""Application settings.

Every secret is read from ``backend/.env``. Nothing is hard-coded and no key is
ever sent to the frontend - the React app only ever sees the *status* of a key
(configured / not configured) and a masked preview.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BACKEND_DIR / "storage"
EVIDENCE_DIR = STORAGE_DIR / "evidence"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DEMO_DIR = STORAGE_DIR / "demo"
LOCAL_DB_DIR = STORAGE_DIR / "local_db"

for _directory in (STORAGE_DIR, EVIDENCE_DIR, UPLOAD_DIR, DEMO_DIR, LOCAL_DB_DIR):
    _directory.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Empty placeholders in .env (GROQ_API_KEY=, GROQ_MODEL=, ...) must not
        # override the code defaults with blank strings.
        env_ignore_empty=True,
    )

    # ---------------- AI ----------------
    groq_api_key: str = ""
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    groq_text_model: str = "llama-3.3-70b-versatile"

    # ---------------- ANPR ----------------
    plate_recognizer_api_key: str = ""
    plate_recognizer_regions: str = "in"

    # ---------------- SMS ----------------
    sms_api_key: str = ""
    sms_sender_id: str = ""
    sms_provider: str = "fast2sms"

    # ---------------- Payment ----------------
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # ---------------- Database ----------------
    mongo_uri: str = ""
    mongo_db_name: str = "rto_echallan"

    # ---------------- Auth ----------------
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # ---------------- Application ----------------
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    detection_interval_seconds: float = 8.0
    detection_cooldown_seconds: float = 90.0
    detection_min_confidence: float = 0.55
    auto_challan: bool = True

    # ---------------- Derived helpers ----------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_jwt_secret(self) -> str:
        """Return the configured secret, or a per-process development secret.

        A generated secret means every backend restart invalidates old tokens,
        which is fine for development and loudly documented in the README.
        """
        if self.jwt_secret.strip():
            return self.jwt_secret.strip()
        return _DEV_JWT_SECRET

    @property
    def jwt_secret_is_generated(self) -> bool:
        return not self.jwt_secret.strip()

    # -------- feature availability (used by /api/config/status) --------
    @property
    def ai_configured(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def anpr_configured(self) -> bool:
        return bool(self.plate_recognizer_api_key.strip())

    @property
    def sms_configured(self) -> bool:
        return bool(self.sms_api_key.strip())

    @property
    def payment_configured(self) -> bool:
        return bool(self.razorpay_key_id.strip() and self.razorpay_key_secret.strip())

    @property
    def mongo_configured(self) -> bool:
        return bool(self.mongo_uri.strip())


_DEV_JWT_SECRET = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def mask_secret(value: str, visible: int = 4) -> str:
    """Return a masked preview of a secret; never returns the raw value."""
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * max(len(value) - visible, 4)}{value[-visible:]}"
