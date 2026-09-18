"""Database access layer.

MongoDB (via Motor) is the primary backend. If ``MONGO_URI`` is empty or the
server cannot be reached, the application transparently falls back to the
bundled JSON store from ``local_store.py`` so that the project is still fully
demonstrable. The active backend is always reported through
``/api/network/status`` and on the Settings page, so nothing is hidden.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import LOCAL_DB_DIR, settings
from .local_store import LocalDatabase, new_id
from .utils import utcnow_iso

logger = logging.getLogger("rto.database")

# Collection names -----------------------------------------------------------
USERS = "users"
CAMERAS = "cameras"
VIOLATIONS = "violations"
CHALLANS = "challans"
VEHICLES = "vehicles"
RULES = "violation_rules"
ALERTS = "maintenance_alerts"
SMS_LOGS = "sms_logs"
PAYMENTS = "payments"
AUDIT = "audit_logs"
OTPS = "otp_codes"
SETTINGS_COL = "app_settings"
COUNTERS = "counters"

ALL_COLLECTIONS = [
    USERS,
    CAMERAS,
    VIOLATIONS,
    CHALLANS,
    VEHICLES,
    RULES,
    ALERTS,
    SMS_LOGS,
    PAYMENTS,
    AUDIT,
    OTPS,
    SETTINGS_COL,
    COUNTERS,
]


class Database:
    """Holds the active database handle and reports which backend is in use."""

    def __init__(self) -> None:
        self.client: Any = None
        self.db: Any = None
        self.backend: str = "unknown"
        self.error: str | None = None
        self.connected_at: str | None = None

    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        if settings.mongo_configured:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient

                client = AsyncIOMotorClient(
                    settings.mongo_uri,
                    serverSelectionTimeoutMS=4000,
                    uuidRepresentation="standard",
                )
                await client.admin.command("ping")
                self.client = client
                self.db = client[settings.mongo_db_name]
                self.backend = "mongodb"
                self.error = None
                self.connected_at = utcnow_iso()
                logger.info("Connected to MongoDB database '%s'", settings.mongo_db_name)
                await self._create_indexes()
                return
            except Exception as exc:  # noqa: BLE001 - report, then fall back
                self.error = f"{type(exc).__name__}: {exc}"
                logger.warning("MongoDB unavailable (%s) - using local JSON store", exc)
        else:
            self.error = "MONGO_URI is empty in backend/.env"
            logger.warning("MONGO_URI not configured - using local JSON store")

        self.db = LocalDatabase(LOCAL_DB_DIR)
        self.client = None
        self.backend = "local-json"
        self.connected_at = utcnow_iso()

    async def _create_indexes(self) -> None:
        try:
            await self.db[USERS].create_index("user_id", unique=True)
            await self.db[CAMERAS].create_index("camera_id", unique=True)
            await self.db[VIOLATIONS].create_index("detected_at")
            await self.db[CHALLANS].create_index("challan_number", unique=True)
            await self.db[VEHICLES].create_index("plate_number", unique=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Index creation skipped: %s", exc)

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()

    # ------------------------------------------------------------------ #
    def collection(self, name: str) -> Any:
        if self.db is None:
            raise RuntimeError("Database is not initialised yet")
        return self.db[name]

    @property
    def using_mongo(self) -> bool:
        return self.backend == "mongodb"

    async def health(self) -> dict:
        info: dict[str, Any] = {
            "backend": self.backend,
            "database_name": settings.mongo_db_name,
            "mongo_uri_configured": settings.mongo_configured,
            "connected_at": self.connected_at,
            "error": self.error,
            "healthy": False,
        }
        try:
            if self.using_mongo:
                await self.client.admin.command("ping")
            else:
                await self.collection(SETTINGS_COL).count_documents({})
            info["healthy"] = True
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)
        return info

    async def next_sequence(self, name: str) -> int:
        """Monotonic counter used for challan numbers."""
        counters = self.collection(COUNTERS)
        await counters.update_one({"_id": name}, {"$inc": {"value": 1}}, upsert=True)
        document = await counters.find_one({"_id": name})
        return int((document or {}).get("value") or 1)


database = Database()


def coll(name: str) -> Any:
    """Shortcut used throughout the routers."""
    return database.collection(name)


__all__ = [
    "database",
    "coll",
    "new_id",
    "USERS",
    "CAMERAS",
    "VIOLATIONS",
    "CHALLANS",
    "VEHICLES",
    "RULES",
    "ALERTS",
    "SMS_LOGS",
    "PAYMENTS",
    "AUDIT",
    "OTPS",
    "SETTINGS_COL",
    "COUNTERS",
    "ALL_COLLECTIONS",
]
