"""E-challan issuing, listing, status changes and SMS re-sending."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..constants import (
    CHALLAN_CANCELLED,
    CHALLAN_DISPUTED,
    CHALLAN_PAID,
    CHALLAN_PENDING,
    CHALLAN_STATUSES,
    VIOLATION_LABELS,
)
from ..database import CHALLANS, VIOLATIONS, coll
from ..deps import get_current_user, require_admin
from ..schemas import ChallanCreateBody, ChallanStatusBody
from ..services import sms_service
from ..services.app_settings import get_settings_document
from ..services.challan_service import is_overdue, issue_challan
from ..utils import day_start_iso, serialize, serialize_many, to_display_ist, utcnow_iso

router = APIRouter(prefix="/api/challans", tags=["Challans"])


@router.get("")
async def list_challans(
    challan_status: str | None = Query(default=None, alias="status"),
    camera_id: str | None = None,
    plate: str | None = None,
    violation_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(get_current_user),
) -> dict:
    query: dict = {}
    if challan_status:
        query["status"] = challan_status
    if camera_id:
        query["camera_id"] = camera_id
    if violation_type:
        query["violation_type"] = violation_type
    if plate:
        query["plate_number"] = {"$regex": plate.upper(), "$options": "i"}
    if date_from or date_to:
        window: dict = {}
        if date_from:
            window["$gte"] = f"{date_from}T00:00:00"
        if date_to:
            window["$lte"] = f"{date_to}T23:59:59"
        query["issued_at"] = window

    total = await coll(CHALLANS).count_documents(query)
    documents = (
        await coll(CHALLANS)
        .find(query)
        .sort("issued_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    challans = serialize_many(documents)
    for challan in challans:
        challan["overdue"] = is_overdue(challan)
        challan["issued_at_display"] = to_display_ist(challan.get("issued_at"))

    return {
        "challans": challans,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": max((total + limit - 1) // limit, 1),
    }


@router.get("/stats")
async def challan_stats(_: dict = Depends(get_current_user)) -> dict:
    documents = await coll(CHALLANS).find({}).to_list(20000)
    today = day_start_iso()

    by_status = {status_name: 0 for status_name in CHALLAN_STATUSES}
    by_type: dict[str, int] = {}
    total_fine = 0.0
    collected = 0.0
    pending_amount = 0.0

    for document in documents:
        status_name = document.get("status", CHALLAN_PENDING)
        by_status[status_name] = by_status.get(status_name, 0) + 1
        by_type[document.get("violation_type", "")] = (
            by_type.get(document.get("violation_type", ""), 0) + 1
        )
        amount = float(document.get("fine_amount") or 0)
        total_fine += amount
        if status_name == CHALLAN_PAID:
            collected += float(document.get("amount_paid") or amount)
        elif status_name == CHALLAN_PENDING:
            pending_amount += amount

    return {
        "total": len(documents),
        "today": sum(1 for item in documents if (item.get("issued_at") or "") >= today),
        "by_status": by_status,
        "by_type": [
            {"code": code, "label": VIOLATION_LABELS.get(code, code), "count": count}
            for code, count in sorted(by_type.items())
        ],
        "total_fine_amount": round(total_fine, 2),
        "collected_amount": round(collected, 2),
        "pending_amount": round(pending_amount, 2),
        "overdue": sum(1 for item in documents if is_overdue(item)),
    }


@router.post("")
async def create_challan(
    body: ChallanCreateBody, user: dict = Depends(get_current_user)
) -> dict:
    violation = await coll(VIOLATIONS).find_one({"_id": body.violation_id})
    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")

    if body.plate_number:
        violation["plate_number"] = body.plate_number.upper()
        await coll(VIOLATIONS).update_one(
            {"_id": body.violation_id},
            {
                "$set": {
                    "plate_number": body.plate_number.upper(),
                    "plate_source": "OFFICER_CORRECTED",
                }
            },
        )

    if not violation.get("plate_number"):
        raise HTTPException(
            status_code=400,
            detail="A number plate is required before a challan can be issued.",
        )

    outcome = await issue_challan(
        violation,
        actor=user["user_id"],
        fine_amount=body.fine_amount,
        owner_name=body.owner_name,
        owner_phone=body.owner_phone,
        send_sms=body.send_sms,
    )
    if not outcome["created"]:
        raise HTTPException(status_code=409, detail=outcome["reason"])
    return outcome


@router.get("/{challan_id}")
async def get_challan(challan_id: str, _: dict = Depends(get_current_user)) -> dict:
    document = await coll(CHALLANS).find_one({"_id": challan_id})
    if not document:
        raise HTTPException(status_code=404, detail="Challan not found")

    challan = serialize(document) or {}
    challan["overdue"] = is_overdue(challan)
    challan["issued_at_display"] = to_display_ist(challan.get("issued_at"))
    challan["detected_at_display"] = to_display_ist(challan.get("detected_at"))
    challan["office"] = await get_settings_document()
    if document.get("violation_id"):
        challan["violation"] = serialize(
            await coll(VIOLATIONS).find_one({"_id": document["violation_id"]}) or {}
        )
    return challan


@router.patch("/{challan_id}/status")
async def update_status(
    challan_id: str, body: ChallanStatusBody, user: dict = Depends(get_current_user)
) -> dict:
    if body.status not in CHALLAN_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"status must be one of {', '.join(CHALLAN_STATUSES)}"
        )

    document = await coll(CHALLANS).find_one({"_id": challan_id})
    if not document:
        raise HTTPException(status_code=404, detail="Challan not found")
    if document.get("status") == CHALLAN_PAID and body.status != CHALLAN_PAID:
        raise HTTPException(status_code=409, detail="A paid challan cannot be reopened")

    changes = {
        "status": body.status,
        "remarks": body.remarks,
        "updated_at": utcnow_iso(),
        "updated_by": user["user_id"],
    }
    if body.status in {CHALLAN_CANCELLED, CHALLAN_DISPUTED}:
        changes["closed_at"] = utcnow_iso()
    await coll(CHALLANS).update_one({"_id": challan_id}, {"$set": changes})
    return {"updated": True, "challan": serialize(await coll(CHALLANS).find_one({"_id": challan_id}))}


@router.post("/{challan_id}/resend-sms")
async def resend_sms(challan_id: str, user: dict = Depends(get_current_user)) -> dict:
    document = await coll(CHALLANS).find_one({"_id": challan_id})
    if not document:
        raise HTTPException(status_code=404, detail="Challan not found")
    phone = (document.get("owner_phone") or "").strip()
    if not phone:
        raise HTTPException(
            status_code=400,
            detail="No owner mobile number on this challan. Update the vehicle record first.",
        )

    message = sms_service.challan_message(
        challan_number=document.get("challan_number", ""),
        plate_number=document.get("plate_number", ""),
        violation_label=document.get("violation_label", ""),
        fine_amount=float(document.get("fine_amount") or 0),
        location=document.get("location") or document.get("camera_id", ""),
        when=to_display_ist(document.get("detected_at")),
        due_date=document.get("due_date", ""),
    )
    outcome = await sms_service.send_sms(
        phone, message, purpose="challan_resend", reference=document.get("challan_number", "")
    )
    await coll(CHALLANS).update_one(
        {"_id": challan_id},
        {
            "$set": {
                "sms_status": "SENT"
                if outcome["ok"]
                else ("DEMO_NOT_SENT" if not outcome["configured"] else "FAILED"),
                "sms_detail": outcome["message"],
                "sms_last_attempt_at": utcnow_iso(),
                "sms_last_attempt_by": user["user_id"],
            }
        },
    )
    return outcome


@router.delete("/{challan_id}")
async def delete_challan(challan_id: str, _: dict = Depends(require_admin)) -> dict:
    document = await coll(CHALLANS).find_one({"_id": challan_id})
    if not document:
        raise HTTPException(status_code=404, detail="Challan not found")
    if document.get("status") == CHALLAN_PAID:
        raise HTTPException(status_code=409, detail="A paid challan cannot be deleted")

    await coll(CHALLANS).delete_one({"_id": challan_id})
    if document.get("violation_id"):
        await coll(VIOLATIONS).update_one(
            {"_id": document["violation_id"]},
            {"$set": {"status": "APPROVED", "challan_id": None, "challan_number": None}},
        )
    return {"deleted": True, "id": challan_id}
