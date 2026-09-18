"""ANPR (Automatic Number Plate Recognition) via the Plate Recognizer Snapshot API.

When ``PLATE_RECOGNIZER_API_KEY`` is missing the service returns
``configured=False`` / ``demo=True`` together with a *clearly labelled* demo
plate. The demo plate is deterministic (derived from the frame bytes) so the
rest of the pipeline can be demonstrated, and every record it produces is
stamped ``plate_source="DEMO"`` and shown as a demo value in the UI. It is never
presented as a real API result.
"""

from __future__ import annotations

import hashlib
import logging
import time

import httpx

from ..config import settings
from .base import not_configured, result

logger = logging.getLogger("rto.anpr")

PROVIDER = "Plate Recognizer ANPR"
SNAPSHOT_URL = "https://api.platerecognizer.com/v1/plate-reader/"
STATISTICS_URL = "https://api.platerecognizer.com/v1/statistics/"
INSTRUCTION = (
    "Add PLATE_RECOGNIZER_API_KEY to backend/.env (get it from app.platerecognizer.com)."
)

_STATE_CODES = ["KA", "MH", "TN", "AP", "TS", "KL", "DL", "GJ", "RJ", "UP"]
_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def is_configured() -> bool:
    return settings.anpr_configured


def demo_plate(seed_bytes: bytes) -> str:
    """Deterministic, obviously-synthetic plate used only in DEMO MODE."""
    digest = hashlib.sha256(seed_bytes or b"demo").digest()
    state = _STATE_CODES[digest[0] % len(_STATE_CODES)]
    district = digest[1] % 90 + 10
    series = _LETTERS[digest[2] % len(_LETTERS)] + _LETTERS[digest[3] % len(_LETTERS)]
    number = int.from_bytes(digest[4:6], "big") % 9000 + 1000
    return f"{state}{district}{series}{number}"


async def test_connection() -> dict:
    if not is_configured():
        return not_configured(PROVIDER, INSTRUCTION)

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                STATISTICS_URL,
                headers={"Authorization": f"Token {settings.plate_recognizer_api_key.strip()}"},
            )
        latency = int((time.perf_counter() - started) * 1000)
    except httpx.HTTPError as exc:
        return result(
            ok=False, provider=PROVIDER, message=f"Could not reach Plate Recognizer: {exc}"
        )

    if response.status_code == 200:
        body = response.json()
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        return result(
            ok=True,
            provider=PROVIDER,
            message="Connected to Plate Recognizer Snapshot API.",
            data={
                "calls_used": usage.get("calls"),
                "monthly_limit": body.get("total_calls") if isinstance(body, dict) else None,
                "regions": settings.plate_recognizer_regions,
            },
            status_code=200,
            latency_ms=latency,
        )
    return result(
        ok=False,
        provider=PROVIDER,
        message=f"Plate Recognizer rejected the key: HTTP {response.status_code} {response.text[:180]}",
        status_code=response.status_code,
        latency_ms=latency,
    )


async def read_plate(image_bytes: bytes, camera_id: str = "") -> dict:
    """Recognise a number plate from a JPEG frame."""
    if not is_configured():
        payload = not_configured(PROVIDER, INSTRUCTION)
        payload["data"] = {
            "plate_number": demo_plate(image_bytes),
            "plate_source": "DEMO",
            "confidence": None,
            "region": settings.plate_recognizer_regions.upper(),
            "note": "Demo plate generated locally - not a Plate Recognizer result.",
        }
        return payload

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(
                SNAPSHOT_URL,
                headers={"Authorization": f"Token {settings.plate_recognizer_api_key.strip()}"},
                files={"upload": ("frame.jpg", image_bytes, "image/jpeg")},
                data={
                    "regions": settings.plate_recognizer_regions,
                    "camera_id": camera_id or "rto-camera",
                },
            )
        latency = int((time.perf_counter() - started) * 1000)
    except httpx.HTTPError as exc:
        return result(ok=False, provider=PROVIDER, message=f"ANPR request failed: {exc}")

    if response.status_code not in (200, 201):
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"ANPR error HTTP {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
            latency_ms=latency,
        )

    body = response.json()
    candidates = body.get("results") or []
    if not candidates:
        return result(
            ok=True,
            provider=PROVIDER,
            message="No number plate found in the frame.",
            data={"plate_number": "", "plate_source": "ANPR", "confidence": None},
            status_code=response.status_code,
            latency_ms=latency,
        )

    best = max(candidates, key=lambda item: item.get("score") or 0)
    return result(
        ok=True,
        provider=PROVIDER,
        message="Number plate recognised.",
        data={
            "plate_number": str(best.get("plate", "")).upper(),
            "plate_source": "ANPR",
            "confidence": round(float(best.get("score") or 0), 3),
            "region": (best.get("region") or {}).get("code", "").upper(),
            "vehicle_type": (best.get("vehicle") or {}).get("type", ""),
            "box": best.get("box"),
            "candidates": [
                {"plate": str(c.get("plate", "")).upper(), "score": c.get("score")}
                for c in candidates[:5]
            ],
        },
        status_code=response.status_code,
        latency_ms=latency,
    )
