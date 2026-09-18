"""Payment endpoints backed by Razorpay (Test Mode) plus an offline counter mode."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..constants import CHALLAN_PAID, CHALLAN_PENDING
from ..database import CHALLANS, PAYMENTS, VEHICLES, coll
from ..deps import get_current_user
from ..schemas import PaymentInitBody, PaymentVerifyBody
from ..services import payment_service, sms_service
from ..utils import serialize, serialize_many, utcnow_iso

router = APIRouter(prefix="/api/payments", tags=["Payments"])


async def _challan(challan_id: str) -> dict:
    document = await coll(CHALLANS).find_one({"_id": challan_id})
    if not document:
        raise HTTPException(status_code=404, detail="Challan not found")
    return document


@router.get("")
async def list_payments(_: dict = Depends(get_current_user)) -> dict:
    documents = await coll(PAYMENTS).find({}).sort("created_at", -1).to_list(500)
    return {"payments": serialize_many(documents), "total": len(documents)}


@router.post("/create-order")
async def create_order(body: PaymentInitBody, user: dict = Depends(get_current_user)) -> dict:
    challan = await _challan(body.challan_id)
    if challan.get("status") == CHALLAN_PAID:
        raise HTTPException(status_code=409, detail="This challan is already paid")

    amount = float(challan.get("fine_amount") or 0)
    outcome = await payment_service.create_order(
        amount_rupees=amount,
        receipt=challan.get("challan_number", body.challan_id),
        notes={
            "challan_number": challan.get("challan_number", ""),
            "plate_number": challan.get("plate_number", ""),
            "violation": challan.get("violation_label", ""),
        },
    )

    record = {
        "challan_id": body.challan_id,
        "challan_number": challan.get("challan_number", ""),
        "plate_number": challan.get("plate_number", ""),
        "amount": amount,
        "gateway": "razorpay",
        "mode": outcome["data"].get("mode", "TEST" if outcome["configured"] else "DEMO"),
        "order_id": outcome["data"].get("order_id", ""),
        "status": "ORDER_CREATED" if outcome["ok"] else "ORDER_FAILED",
        "configured": outcome["configured"],
        "detail": outcome["message"],
        "created_by": user["user_id"],
        "created_at": utcnow_iso(),
    }
    await coll(PAYMENTS).insert_one(record)

    return {
        **outcome,
        "challan": {
            "id": body.challan_id,
            "challan_number": challan.get("challan_number", ""),
            "plate_number": challan.get("plate_number", ""),
            "owner_name": challan.get("owner_name", ""),
            "owner_phone": challan.get("owner_phone", ""),
            "violation_label": challan.get("violation_label", ""),
            "fine_amount": amount,
        },
    }


async def _mark_paid(
    challan: dict, payment_details: dict, actor: str, notify: bool = True
) -> dict:
    amount = float(challan.get("fine_amount") or 0)
    await coll(CHALLANS).update_one(
        {"_id": challan["_id"]},
        {
            "$set": {
                "status": CHALLAN_PAID,
                "amount_paid": amount,
                "paid_at": utcnow_iso(),
                "paid_via": payment_details.get("method", "razorpay"),
                "payment": payment_details,
                "updated_at": utcnow_iso(),
                "updated_by": actor,
            }
        },
    )
    if challan.get("plate_number"):
        await coll(VEHICLES).update_one(
            {"plate_number": challan["plate_number"]},
            {"$inc": {"total_paid": amount}, "$set": {"updated_at": utcnow_iso()}},
        )

    sms_outcome = None
    if notify and challan.get("owner_phone"):
        sms_outcome = await sms_service.send_sms(
            challan["owner_phone"],
            (
                f"Payment received for challan {challan.get('challan_number')} "
                f"(Rs.{int(amount)}). Thank you. - RTO E-Challan"
            ),
            purpose="payment_receipt",
            reference=challan.get("challan_number", ""),
        )

    updated = await coll(CHALLANS).find_one({"_id": challan["_id"]})
    return {"challan": serialize(updated), "sms": sms_outcome}


@router.post("/verify")
async def verify_payment(body: PaymentVerifyBody, user: dict = Depends(get_current_user)) -> dict:
    challan = await _challan(body.challan_id)
    if challan.get("status") == CHALLAN_PAID:
        return {
            "verified": True,
            "already_paid": True,
            "challan": serialize(challan),
        }

    if not payment_service.is_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Razorpay is not configured, so an online payment cannot be verified. "
                "Use 'Record offline payment' for the demo, or add RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET to backend/.env."
            ),
        )

    valid = payment_service.verify_signature(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    )
    await coll(PAYMENTS).insert_one(
        {
            "challan_id": body.challan_id,
            "challan_number": challan.get("challan_number", ""),
            "amount": float(challan.get("fine_amount") or 0),
            "gateway": "razorpay",
            "mode": "TEST" if payment_service.is_test_mode() else "LIVE",
            "order_id": body.razorpay_order_id,
            "payment_id": body.razorpay_payment_id,
            "status": "VERIFIED" if valid else "SIGNATURE_MISMATCH",
            "configured": True,
            "detail": "Razorpay signature verified" if valid else "Signature mismatch",
            "created_by": user["user_id"],
            "created_at": utcnow_iso(),
        }
    )

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Razorpay signature verification failed - payment not accepted.",
        )

    outcome = await _mark_paid(
        challan,
        {
            "method": "razorpay",
            "order_id": body.razorpay_order_id,
            "payment_id": body.razorpay_payment_id,
            "mode": "TEST" if payment_service.is_test_mode() else "LIVE",
            "verified_at": utcnow_iso(),
        },
        actor=user["user_id"],
    )
    return {"verified": True, **outcome}


@router.post("/offline")
async def record_offline_payment(
    body: PaymentInitBody,
    method: str = "CASH_COUNTER",
    reference: str = "",
    user: dict = Depends(get_current_user),
) -> dict:
    """Cash/UPI collected at the counter - also used for the demo walkthrough."""
    challan = await _challan(body.challan_id)
    if challan.get("status") == CHALLAN_PAID:
        raise HTTPException(status_code=409, detail="This challan is already paid")
    if challan.get("status") != CHALLAN_PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Only PENDING challans can be collected (current: {challan.get('status')})",
        )

    await coll(PAYMENTS).insert_one(
        {
            "challan_id": body.challan_id,
            "challan_number": challan.get("challan_number", ""),
            "amount": float(challan.get("fine_amount") or 0),
            "gateway": "offline",
            "mode": "OFFLINE",
            "order_id": "",
            "payment_id": reference,
            "status": "COLLECTED",
            "configured": True,
            "detail": f"Collected at counter ({method}) by {user['user_id']}",
            "created_by": user["user_id"],
            "created_at": utcnow_iso(),
        }
    )
    outcome = await _mark_paid(
        challan,
        {
            "method": method,
            "reference": reference,
            "mode": "OFFLINE",
            "collected_by": user["user_id"],
            "verified_at": utcnow_iso(),
        },
        actor=user["user_id"],
    )
    return {"recorded": True, **outcome}
