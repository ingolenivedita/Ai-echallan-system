"""SMS delivery.

A small provider interface is defined so another gateway (MSG91, Twilio, ...)
can be added later without touching the callers. Fast2SMS is the initial
provider. Every send attempt - including the ones refused because the API key is
missing - is written to the ``sms_logs`` collection so the officer can see what
the system tried to do.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import httpx

from ..config import settings
from ..utils import utcnow_iso
from .base import not_configured, result

logger = logging.getLogger("rto.sms")

PROVIDER = "SMS Gateway"
INSTRUCTION = (
    "Add SMS_API_KEY (and optionally SMS_SENDER_ID) to backend/.env "
    "(get it from fast2sms.com/dashboard/dev-api)."
)


def is_configured() -> bool:
    return settings.sms_configured


def normalise_phone(phone: str) -> str:
    digits = "".join(character for character in str(phone or "") if character.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


# --------------------------------------------------------------------------- #
# Provider interface
# --------------------------------------------------------------------------- #
class SmsProvider(ABC):
    name: str = "provider"
    display_name: str = "SMS Provider"

    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def send(self, phone: str, message: str) -> dict: ...

    @abstractmethod
    async def balance(self) -> dict: ...


class Fast2SmsProvider(SmsProvider):
    name = "fast2sms"
    display_name = "Fast2SMS"
    endpoint = "https://www.fast2sms.com/dev/bulkV2"
    wallet_endpoint = "https://www.fast2sms.com/dev/wallet"

    def configured(self) -> bool:
        return bool(settings.sms_api_key.strip())

    def _headers(self) -> dict:
        return {"authorization": settings.sms_api_key.strip()}

    async def send(self, phone: str, message: str) -> dict:
        number = normalise_phone(phone)
        if len(number) != 10:
            return result(
                ok=False,
                provider=self.display_name,
                message=f"'{phone}' is not a valid 10 digit Indian mobile number.",
            )

        sender_id = settings.sms_sender_id.strip()
        payload = {
            "message": message,
            "language": "english",
            "flash": "0",
            "numbers": number,
            # 'dlt' route requires an approved sender id + template; 'q' works
            # for quick transactional testing which is what a demo needs.
            "route": "dlt" if sender_id else "q",
        }
        if sender_id:
            payload["sender_id"] = sender_id

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.endpoint, headers=self._headers(), data=payload
                )
            latency = int((time.perf_counter() - started) * 1000)
        except httpx.HTTPError as exc:
            return result(
                ok=False, provider=self.display_name, message=f"SMS request failed: {exc}"
            )

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:200]}

        succeeded = response.status_code == 200 and bool(body.get("return"))
        return result(
            ok=succeeded,
            provider=self.display_name,
            message=(
                f"SMS accepted by Fast2SMS (id {(body.get('request_id') or '-')})"
                if succeeded
                else f"Fast2SMS rejected the request: {body.get('message') or body}"
            ),
            data={"response": body, "phone": number},
            status_code=response.status_code,
            latency_ms=latency,
        )

    async def balance(self) -> dict:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(self.wallet_endpoint, headers=self._headers())
            latency = int((time.perf_counter() - started) * 1000)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return result(
                ok=False, provider=self.display_name, message=f"Wallet check failed: {exc}"
            )

        if response.status_code == 200 and body.get("return"):
            return result(
                ok=True,
                provider=self.display_name,
                message=f"Connected. Wallet balance: {body.get('wallet')}",
                data={"wallet": body.get("wallet"), "sender_id": settings.sms_sender_id},
                status_code=200,
                latency_ms=latency,
            )
        return result(
            ok=False,
            provider=self.display_name,
            message=f"Fast2SMS rejected the key: {body.get('message') or body}",
            status_code=response.status_code,
            latency_ms=latency,
        )


PROVIDERS: dict[str, SmsProvider] = {Fast2SmsProvider.name: Fast2SmsProvider()}


def get_provider() -> SmsProvider:
    return PROVIDERS.get(settings.sms_provider.strip().lower(), PROVIDERS["fast2sms"])


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
async def _log(entry: dict) -> None:
    try:
        from ..database import SMS_LOGS, coll

        await coll(SMS_LOGS).insert_one(entry)
    except Exception as exc:  # noqa: BLE001 - logging must never break a send
        logger.warning("Could not persist SMS log: %s", exc)


async def send_sms(
    phone: str, message: str, purpose: str = "general", reference: str = ""
) -> dict:
    provider = get_provider()

    if not provider.configured():
        payload = not_configured(f"{provider.display_name} SMS", INSTRUCTION)
        payload["data"] = {
            "phone": normalise_phone(phone),
            "message": message,
            "delivery": "NOT_SENT_DEMO_MODE",
        }
        await _log(
            {
                "phone": normalise_phone(phone),
                "message": message,
                "purpose": purpose,
                "reference": reference,
                "provider": provider.display_name,
                "status": "DEMO_NOT_SENT",
                "detail": payload["message"],
                "created_at": utcnow_iso(),
            }
        )
        return payload

    outcome = await provider.send(phone, message)
    await _log(
        {
            "phone": normalise_phone(phone),
            "message": message,
            "purpose": purpose,
            "reference": reference,
            "provider": provider.display_name,
            "status": "SENT" if outcome["ok"] else "FAILED",
            "detail": outcome["message"],
            "created_at": utcnow_iso(),
        }
    )
    return outcome


async def test_connection() -> dict:
    provider = get_provider()
    if not provider.configured():
        return not_configured(f"{provider.display_name} SMS", INSTRUCTION)
    return await provider.balance()


def challan_message(
    challan_number: str,
    plate_number: str,
    violation_label: str,
    fine_amount: float,
    location: str,
    when: str,
    due_date: str,
) -> str:
    return (
        f"RTO E-CHALLAN {challan_number}\n"
        f"Vehicle: {plate_number}\n"
        f"Violation: {violation_label}\n"
        f"Location: {location}\n"
        f"Date/Time: {when}\n"
        f"Fine: Rs.{int(fine_amount)}\n"
        f"Pay before {due_date} on the RTO e-challan portal."
    )
