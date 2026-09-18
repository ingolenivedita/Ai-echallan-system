"""Admin -> API Configuration.

Reports which external APIs are configured, exposes a Test Connection action for
each, and shows a masked preview of every key. Raw secrets are never returned.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import mask_secret, settings
from ..database import SMS_LOGS, coll, database
from ..deps import get_current_user, require_admin
from ..schemas import SmsTestBody
from ..services import ai_service, anpr_service, payment_service, sms_service
from ..utils import serialize_many, utcnow_iso

router = APIRouter(prefix="/api/config", tags=["API Configuration"])

# last Test Connection outcome per service, for the status page
_last_tests: dict[str, dict] = {}

SERVICES = {
    "ai": {
        "key": "ai",
        "name": "Groq AI API",
        "purpose": "AI reasoning and vision based violation detection",
        "env_keys": ["GROQ_API_KEY", "GROQ_MODEL"],
        "docs_url": "https://console.groq.com/keys",
        "instructions": [
            "Create a free account at console.groq.com",
            "Open API Keys and create a new key",
            "Paste it into backend/.env as GROQ_API_KEY=your_key",
            "Restart the backend, then press Test Connection",
        ],
        "demo_behaviour": (
            "Without this key, detection falls back to the OpenCV heuristic detector "
            "or the demo simulator for synthetic cameras."
        ),
    },
    "anpr": {
        "key": "anpr",
        "name": "Plate Recognizer ANPR API",
        "purpose": "Reads vehicle number plates from evidence frames",
        "env_keys": ["PLATE_RECOGNIZER_API_KEY", "PLATE_RECOGNIZER_REGIONS"],
        "docs_url": "https://app.platerecognizer.com/start/",
        "instructions": [
            "Sign up at app.platerecognizer.com (free tier available)",
            "Copy the API token from the dashboard",
            "Paste it into backend/.env as PLATE_RECOGNIZER_API_KEY=your_token",
            "Restart the backend, then press Test Connection",
        ],
        "demo_behaviour": (
            "Without this key the system labels plates as DEMO values instead of "
            "claiming a real ANPR read."
        ),
    },
    "sms": {
        "key": "sms",
        "name": "SMS API (Fast2SMS)",
        "purpose": "Delivers challan notices and login OTPs to vehicle owners/officers",
        "env_keys": ["SMS_API_KEY", "SMS_SENDER_ID", "SMS_PROVIDER"],
        "docs_url": "https://www.fast2sms.com/dashboard/dev-api",
        "instructions": [
            "Create an account at fast2sms.com",
            "Open Dev API and copy the Authorization key",
            "Paste it into backend/.env as SMS_API_KEY=your_key",
            "Optionally set SMS_SENDER_ID for the DLT route",
            "Restart the backend, then press Test Connection",
        ],
        "demo_behaviour": (
            "Without this key every message is logged with status DEMO_NOT_SENT - "
            "nothing is silently dropped and no delivery is faked."
        ),
    },
    "payment": {
        "key": "payment",
        "name": "Razorpay Payment API",
        "purpose": "Online challan payment in Razorpay Test Mode",
        "env_keys": ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"],
        "docs_url": "https://dashboard.razorpay.com/app/website-app-settings/api-keys",
        "instructions": [
            "Sign up at razorpay.com and stay in Test Mode",
            "Settings -> API Keys -> Generate Test Key",
            "Paste both values into backend/.env (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)",
            "Restart the backend, then press Test Connection",
        ],
        "demo_behaviour": (
            "Without these keys online payment is disabled; officers can still record "
            "an offline counter payment."
        ),
    },
}

TESTERS = {
    "ai": ai_service.test_connection,
    "anpr": anpr_service.test_connection,
    "sms": sms_service.test_connection,
    "payment": payment_service.test_connection,
}


def _service_state(key: str) -> dict:
    definition = SERVICES[key]
    if key == "ai":
        configured = settings.ai_configured
        masked = mask_secret(settings.groq_api_key)
        extra = {"model": settings.groq_model, "text_model": settings.groq_text_model}
    elif key == "anpr":
        configured = settings.anpr_configured
        masked = mask_secret(settings.plate_recognizer_api_key)
        extra = {"regions": settings.plate_recognizer_regions}
    elif key == "sms":
        configured = settings.sms_configured
        masked = mask_secret(settings.sms_api_key)
        extra = {
            "provider": sms_service.get_provider().display_name,
            "sender_id": settings.sms_sender_id or "(not set)",
        }
    else:
        configured = settings.payment_configured
        masked = mask_secret(settings.razorpay_key_secret)
        extra = {
            "key_id": mask_secret(settings.razorpay_key_id) or "(not set)",
            "mode": "TEST" if payment_service.is_test_mode() else "LIVE/UNKNOWN",
        }

    return {
        **definition,
        "configured": configured,
        "status": "CONNECTED" if configured else "NOT_CONNECTED",
        "masked_key": masked or "(empty)",
        "extra": extra,
        "last_test": _last_tests.get(key),
    }


@router.get("/status")
async def config_status(_: dict = Depends(get_current_user)) -> dict:
    db_health = await database.health()
    return {
        "services": [_service_state(key) for key in SERVICES],
        "summary": {
            "configured": sum(1 for key in SERVICES if _service_state(key)["configured"]),
            "total": len(SERVICES),
        },
        "database": {
            "backend": db_health["backend"],
            "healthy": db_health["healthy"],
            "mongo_uri_configured": db_health["mongo_uri_configured"],
            "database_name": db_health["database_name"],
            "masked_uri": mask_secret(settings.mongo_uri, visible=8) or "(empty)",
            "error": db_health["error"],
            "note": (
                "MONGO_URI is empty, so the bundled local JSON store is being used. "
                "Add a MongoDB URI in backend/.env to switch to MongoDB."
                if not db_health["mongo_uri_configured"]
                else ""
            ),
        },
        "auth": {
            "jwt_configured": not settings.jwt_secret_is_generated,
            "masked_secret": mask_secret(settings.jwt_secret) or "(auto-generated)",
            "algorithm": settings.jwt_algorithm,
            "token_lifetime_minutes": settings.access_token_expire_minutes,
            "note": (
                "JWT_SECRET is empty, so a temporary secret is generated at startup - "
                "sessions end when the backend restarts. Set JWT_SECRET in backend/.env."
                if settings.jwt_secret_is_generated
                else ""
            ),
        },
        "env_file": "backend/.env",
        "checked_at": utcnow_iso(),
    }


@router.post("/test/{service}")
async def test_service(service: str, _: dict = Depends(require_admin)) -> dict:
    service = service.lower()
    if service not in TESTERS:
        raise HTTPException(
            status_code=404, detail=f"Unknown service. Use one of: {', '.join(TESTERS)}"
        )
    outcome = await TESTERS[service]()
    _last_tests[service] = outcome
    return outcome


@router.post("/test-all")
async def test_all(_: dict = Depends(require_admin)) -> dict:
    results = {}
    for key, tester in TESTERS.items():
        outcome = await tester()
        _last_tests[key] = outcome
        results[key] = outcome
    return {"results": results, "checked_at": utcnow_iso()}


@router.post("/sms/send-test")
async def send_test_sms(body: SmsTestBody, admin: dict = Depends(require_admin)) -> dict:
    outcome = await sms_service.send_sms(
        body.phone, body.message, purpose="test", reference=admin["user_id"]
    )
    _last_tests["sms"] = outcome
    return outcome


@router.get("/sms/logs")
async def sms_logs(limit: int = 100, _: dict = Depends(get_current_user)) -> dict:
    documents = (
        await coll(SMS_LOGS)
        .find({})
        .sort("created_at", -1)
        .limit(min(limit, 500))
        .to_list(500)
    )
    everything = await coll(SMS_LOGS).find({}).to_list(2000)
    return {
        "logs": serialize_many(documents),
        "summary": {
            "total": len(everything),
            "sent": sum(1 for item in everything if item.get("status") == "SENT"),
            "failed": sum(1 for item in everything if item.get("status") == "FAILED"),
            "demo_not_sent": sum(
                1 for item in everything if item.get("status") == "DEMO_NOT_SENT"
            ),
        },
    }
