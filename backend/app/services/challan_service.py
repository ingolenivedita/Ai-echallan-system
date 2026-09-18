"""Challan generation: turns an approved violation into a payable e-challan."""

from __future__ import annotations

import logging
from datetime import timedelta

from ..constants import (
    CHALLAN_PENDING,
    VIOLATION_CHALLANED,
    VIOLATION_LABELS,
)
from ..database import CHALLANS, VEHICLES, VIOLATIONS, coll, database
from ..utils import (
    generate_challan_number,
    parse_iso,
    serialize,
    to_display_ist,
    utcnow,
    utcnow_iso,
)
from . import sms_service
from .app_settings import get_settings_document
from .rules_service import get_rule

logger = logging.getLogger("rto.challan")


async def existing_challan_for_violation(violation_id: str) -> dict | None:
    return await coll(CHALLANS).find_one({"violation_id": violation_id})


async def lookup_vehicle(plate_number: str) -> dict | None:
    if not plate_number:
        return None
    return await coll(VEHICLES).find_one({"plate_number": plate_number.upper()})


async def issue_challan(
    violation: dict,
    actor: str = "system",
    fine_amount: float | None = None,
    owner_name: str = "",
    owner_phone: str = "",
    send_sms: bool = True,
) -> dict:
    """Create a challan for ``violation`` (a raw database document)."""
    violation_id = str(violation.get("_id") or violation.get("id") or "")
    duplicate = await existing_challan_for_violation(violation_id)
    if duplicate:
        return {
            "created": False,
            "reason": "A challan already exists for this violation.",
            "challan": serialize(duplicate),
            "sms": None,
        }

    violation_type = violation.get("violation_type", "")
    rule = await get_rule(violation_type)
    app_settings = await get_settings_document()

    plate_number = (violation.get("plate_number") or "").upper()
    vehicle = await lookup_vehicle(plate_number)

    amount = float(
        fine_amount if fine_amount is not None else rule.get("fine_amount") or 500
    )
    due_days = int(app_settings.get("challan_due_days") or 30)
    due_date = (utcnow() + timedelta(days=due_days)).strftime("%Y-%m-%d")

    sequence = await database.next_sequence("challan")
    challan_number = generate_challan_number(sequence)

    resolved_owner = owner_name or (vehicle or {}).get("owner_name", "")
    resolved_phone = owner_phone or (vehicle or {}).get("owner_phone", "")

    document = {
        "challan_number": challan_number,
        "violation_id": violation_id,
        "violation_type": violation_type,
        "violation_label": VIOLATION_LABELS.get(violation_type, violation_type),
        "section": rule.get("section", ""),
        "camera_id": violation.get("camera_id", ""),
        "camera_name": violation.get("camera_name", ""),
        "location": violation.get("location", ""),
        "plate_number": plate_number,
        "plate_source": violation.get("plate_source", ""),
        "owner_name": resolved_owner,
        "owner_phone": resolved_phone,
        "vehicle_type": violation.get("vehicle_type", ""),
        "fine_amount": amount,
        "amount_paid": 0.0,
        "status": CHALLAN_PENDING,
        "confidence": violation.get("confidence"),
        "detector": violation.get("detector", ""),
        "simulated": bool(violation.get("simulated")),
        "evidence_image": violation.get("evidence_image", ""),
        "detected_at": violation.get("detected_at"),
        "issued_at": utcnow_iso(),
        "issued_by": actor,
        "due_date": due_date,
        "sms_status": "NOT_SENT",
        "sms_detail": "",
        "payment": {},
        "remarks": "",
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }

    inserted = await coll(CHALLANS).insert_one(document)
    document["_id"] = inserted.inserted_id

    await coll(VIOLATIONS).update_one(
        {"_id": violation_id},
        {
            "$set": {
                "status": VIOLATION_CHALLANED,
                "challan_id": str(inserted.inserted_id),
                "challan_number": challan_number,
                "updated_at": utcnow_iso(),
            }
        },
    )

    await _register_vehicle_activity(plate_number, violation, amount)

    sms_outcome = None
    if send_sms and app_settings.get("sms_on_challan", True) and resolved_phone:
        message = sms_service.challan_message(
            challan_number=challan_number,
            plate_number=plate_number or "UNKNOWN",
            violation_label=document["violation_label"],
            fine_amount=amount,
            location=document["location"] or document["camera_id"],
            when=to_display_ist(document["detected_at"]),
            due_date=due_date,
        )
        sms_outcome = await sms_service.send_sms(
            resolved_phone, message, purpose="challan", reference=challan_number
        )
        await coll(CHALLANS).update_one(
            {"_id": inserted.inserted_id},
            {
                "$set": {
                    "sms_status": "SENT"
                    if sms_outcome["ok"]
                    else ("DEMO_NOT_SENT" if not sms_outcome["configured"] else "FAILED"),
                    "sms_detail": sms_outcome["message"],
                    "updated_at": utcnow_iso(),
                }
            },
        )
        document["sms_status"] = (
            "SENT" if sms_outcome["ok"] else ("DEMO_NOT_SENT" if not sms_outcome["configured"] else "FAILED")
        )
        document["sms_detail"] = sms_outcome["message"]
    elif send_sms and not resolved_phone:
        document["sms_detail"] = "No owner phone number on record for this vehicle."
        await coll(CHALLANS).update_one(
            {"_id": inserted.inserted_id},
            {"$set": {"sms_detail": document["sms_detail"]}},
        )

    return {
        "created": True,
        "reason": "",
        "challan": serialize(document),
        "sms": sms_outcome,
    }


async def _register_vehicle_activity(
    plate_number: str, violation: dict, amount: float
) -> None:
    """Keep the Vehicles register in sync with issued challans."""
    if not plate_number:
        return

    existing = await coll(VEHICLES).find_one({"plate_number": plate_number})
    if existing:
        await coll(VEHICLES).update_one(
            {"_id": existing["_id"]},
            {
                "$inc": {"violation_count": 1, "total_fine": amount},
                "$set": {
                    "last_violation_at": violation.get("detected_at"),
                    "last_violation_type": violation.get("violation_type"),
                    "updated_at": utcnow_iso(),
                },
            },
        )
        return

    await coll(VEHICLES).insert_one(
        {
            "plate_number": plate_number,
            "owner_name": "",
            "owner_phone": "",
            "owner_address": "",
            "vehicle_type": violation.get("vehicle_type") or "Two Wheeler",
            "make_model": "",
            "colour": "",
            "registration_date": "",
            "insurance_valid_till": "",
            "puc_valid_till": "",
            "source": "AUTO_FROM_DETECTION",
            "plate_source": violation.get("plate_source", ""),
            "violation_count": 1,
            "total_fine": amount,
            "last_violation_at": violation.get("detected_at"),
            "last_violation_type": violation.get("violation_type"),
            "created_at": utcnow_iso(),
            "updated_at": utcnow_iso(),
        }
    )


def is_overdue(challan: dict) -> bool:
    if challan.get("status") != CHALLAN_PENDING:
        return False
    due = parse_iso(f"{challan.get('due_date', '')}T00:00:00")
    return bool(due and due < utcnow())
