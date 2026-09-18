"""Shared helpers: timestamps, serialisation, ids, small formatting utilities."""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

# The whole project stores timestamps as ISO-8601 UTC strings. That keeps JSON
# serialisation trivial and makes range queries behave identically on MongoDB
# and on the bundled local store (ISO strings sort chronologically).
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

IST_OFFSET = timedelta(hours=5, minutes=30)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().strftime(ISO_FORMAT)


def iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(ISO_FORMAT)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def day_start_iso(offset_days: int = 0) -> str:
    moment = utcnow() - timedelta(days=offset_days)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0).strftime(
        ISO_FORMAT
    )


def day_key(value: str | None) -> str:
    return (value or "")[:10]


def to_display_ist(value: str | None) -> str:
    """Format a stored UTC timestamp as Indian Standard Time for challans/SMS."""
    moment = parse_iso(value)
    if not moment:
        return "-"
    return (moment + IST_OFFSET).strftime("%d-%m-%Y %H:%M")


def serialize(document: dict | None) -> dict | None:
    """Turn a database document into an API-friendly dict (``_id`` -> ``id``)."""
    if document is None:
        return None
    result = {key: value for key, value in document.items() if key != "_id"}
    result["id"] = str(document.get("_id", ""))
    return result


def serialize_many(documents: Iterable[dict]) -> list[dict]:
    return [serialize(document) for document in documents]  # type: ignore[misc]


def strip_private(document: dict, private_keys: Iterable[str]) -> dict:
    return {key: value for key, value in document.items() if key not in set(private_keys)}


def random_digits(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def generate_challan_number(sequence: int) -> str:
    return f"CH{utcnow().strftime('%Y%m%d')}{sequence:05d}"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def percentage(part: float, whole: float) -> float:
    if not whole:
        return 0.0
    return round((part / whole) * 100, 1)
