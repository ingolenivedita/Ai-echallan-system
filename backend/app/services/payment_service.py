"""Razorpay payment service (Test Mode).

Only ``RAZORPAY_KEY_ID`` is ever returned to the browser - that value is the
publishable key required by Razorpay Checkout. ``RAZORPAY_KEY_SECRET`` stays on
the server and is used for the REST call and for HMAC signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

import httpx

from ..config import mask_secret, settings
from ..utils import utcnow_iso
from .base import not_configured, result

logger = logging.getLogger("rto.payment")

PROVIDER = "Razorpay"
BASE_URL = "https://api.razorpay.com/v1"
INSTRUCTION = (
    "Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (Test Mode) to backend/.env "
    "(get them from dashboard.razorpay.com -> Settings -> API Keys)."
)


def is_configured() -> bool:
    return settings.payment_configured


def _auth() -> tuple[str, str]:
    return settings.razorpay_key_id.strip(), settings.razorpay_key_secret.strip()


def is_test_mode() -> bool:
    return settings.razorpay_key_id.strip().startswith("rzp_test")


async def test_connection() -> dict:
    if not is_configured():
        return not_configured(PROVIDER, INSTRUCTION)

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(
                f"{BASE_URL}/payments", params={"count": 1}, auth=_auth()
            )
        latency = int((time.perf_counter() - started) * 1000)
    except httpx.HTTPError as exc:
        return result(ok=False, provider=PROVIDER, message=f"Could not reach Razorpay: {exc}")

    if response.status_code == 200:
        return result(
            ok=True,
            provider=PROVIDER,
            message=f"Connected in {'TEST' if is_test_mode() else 'LIVE'} mode.",
            data={
                "key_id": mask_secret(settings.razorpay_key_id) or "(not set)",
                "mode": "TEST" if is_test_mode() else "LIVE",
                "payments_visible": (response.json() or {}).get("count"),
            },
            status_code=200,
            latency_ms=latency,
        )

    detail = ""
    try:
        detail = (response.json().get("error") or {}).get("description", "")
    except ValueError:
        detail = response.text[:180]
    return result(
        ok=False,
        provider=PROVIDER,
        message=f"Razorpay rejected the credentials: HTTP {response.status_code} {detail}",
        status_code=response.status_code,
        latency_ms=latency,
    )


async def create_order(
    amount_rupees: float, receipt: str, notes: dict | None = None
) -> dict:
    """Create a Razorpay order. Amount is converted to paise."""
    if not is_configured():
        payload = not_configured(PROVIDER, INSTRUCTION)
        payload["data"] = {
            "order_id": f"demo_order_{int(time.time())}",
            "amount": round(float(amount_rupees), 2),
            "currency": "INR",
            "receipt": receipt,
            "mode": "DEMO",
            "note": "Demo order created locally - no Razorpay order exists.",
            "created_at": utcnow_iso(),
        }
        return payload

    body = {
        "amount": int(round(float(amount_rupees) * 100)),
        "currency": "INR",
        "receipt": receipt[:40],
        "notes": {key: str(value)[:250] for key, value in (notes or {}).items()},
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{BASE_URL}/orders", json=body, auth=_auth())
        latency = int((time.perf_counter() - started) * 1000)
    except httpx.HTTPError as exc:
        return result(ok=False, provider=PROVIDER, message=f"Order creation failed: {exc}")

    if response.status_code not in (200, 201):
        detail = response.text[:200]
        try:
            detail = (response.json().get("error") or {}).get("description", detail)
        except ValueError:
            pass
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"Razorpay order failed: {detail}",
            status_code=response.status_code,
            latency_ms=latency,
        )

    order = response.json()
    return result(
        ok=True,
        provider=PROVIDER,
        message="Razorpay order created.",
        data={
            "order_id": order.get("id"),
            "amount": (order.get("amount") or 0) / 100,
            "currency": order.get("currency", "INR"),
            "receipt": order.get("receipt"),
            "status": order.get("status"),
            # Publishable key - safe for the browser, required by Checkout.
            "key_id": settings.razorpay_key_id.strip(),
            "mode": "TEST" if is_test_mode() else "LIVE",
        },
        status_code=response.status_code,
        latency_ms=latency,
    )


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify the Razorpay Checkout callback signature."""
    secret = settings.razorpay_key_secret.strip()
    if not secret or not order_id or not payment_id or not signature:
        return False
    expected = hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def fetch_payment(payment_id: str) -> dict:
    if not is_configured():
        return not_configured(PROVIDER, INSTRUCTION)
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(f"{BASE_URL}/payments/{payment_id}", auth=_auth())
    except httpx.HTTPError as exc:
        return result(ok=False, provider=PROVIDER, message=f"Lookup failed: {exc}")

    if response.status_code != 200:
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"Payment lookup failed: HTTP {response.status_code}",
            status_code=response.status_code,
        )
    return result(
        ok=True, provider=PROVIDER, message="Payment fetched.", data=response.json()
    )
