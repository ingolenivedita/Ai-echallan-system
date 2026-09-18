"""Common result shape for every external API service.

Rule enforced across all four services: when an API key is missing we return
``configured=False`` with ``demo=True`` and an explicit "API not configured"
message. We never fabricate a successful third-party response.
"""

from __future__ import annotations

from typing import Any

from ..utils import utcnow_iso

NOT_CONFIGURED_MESSAGE = "API not configured"


def result(
    *,
    ok: bool,
    provider: str,
    configured: bool = True,
    demo: bool = False,
    message: str = "",
    data: dict[str, Any] | None = None,
    status_code: int | None = None,
    latency_ms: int | None = None,
) -> dict:
    return {
        "ok": ok,
        "provider": provider,
        "configured": configured,
        "demo": demo,
        "message": message,
        "data": data or {},
        "status_code": status_code,
        "latency_ms": latency_ms,
        "checked_at": utcnow_iso(),
    }


def not_configured(provider: str, instruction: str) -> dict:
    return result(
        ok=False,
        provider=provider,
        configured=False,
        demo=True,
        message=f"{NOT_CONFIGURED_MESSAGE}. {instruction}",
    )
