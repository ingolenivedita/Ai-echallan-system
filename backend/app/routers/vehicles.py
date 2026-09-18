"""Vehicle register: owner details used for challans and SMS delivery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import CHALLANS, VEHICLES, VIOLATIONS, coll
from ..deps import get_current_user, require_admin
from ..schemas import VehicleBody
from ..services.sms_service import normalise_phone
from ..utils import serialize, serialize_many, utcnow_iso

router = APIRouter(prefix="/api/vehicles", tags=["Vehicles"])


@router.get("")
async def list_vehicles(
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(get_current_user),
) -> dict:
    query: dict = {}
    if search:
        needle = search.strip()
        query["$or"] = [
            {"plate_number": {"$regex": needle.upper(), "$options": "i"}},
            {"owner_name": {"$regex": needle, "$options": "i"}},
            {"owner_phone": {"$regex": needle, "$options": "i"}},
        ]

    total = await coll(VEHICLES).count_documents(query)
    documents = (
        await coll(VEHICLES)
        .find(query)
        .sort("updated_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "vehicles": serialize_many(documents),
        "page": page,
        "limit": limit,
        "total": total,
        "pages": max((total + limit - 1) // limit, 1),
    }


@router.post("")
async def create_vehicle(body: VehicleBody, user: dict = Depends(get_current_user)) -> dict:
    plate = body.plate_number.strip().upper().replace(" ", "")
    if await coll(VEHICLES).find_one({"plate_number": plate}):
        raise HTTPException(status_code=409, detail=f"{plate} is already registered")

    document = {
        **body.model_dump(),
        "plate_number": plate,
        "owner_phone": normalise_phone(body.owner_phone),
        "source": "MANUAL",
        "violation_count": 0,
        "total_fine": 0.0,
        "total_paid": 0.0,
        "created_by": user["user_id"],
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }
    inserted = await coll(VEHICLES).insert_one(document)
    document["_id"] = inserted.inserted_id
    return {"created": True, "vehicle": serialize(document)}


@router.get("/{plate_number}")
async def get_vehicle(plate_number: str, _: dict = Depends(get_current_user)) -> dict:
    plate = plate_number.strip().upper()
    document = await coll(VEHICLES).find_one({"plate_number": plate})
    if not document:
        raise HTTPException(status_code=404, detail=f"{plate} is not in the register")

    violations = (
        await coll(VIOLATIONS)
        .find({"plate_number": plate})
        .sort("detected_at", -1)
        .limit(50)
        .to_list(50)
    )
    challans = (
        await coll(CHALLANS)
        .find({"plate_number": plate})
        .sort("issued_at", -1)
        .limit(50)
        .to_list(50)
    )
    vehicle = serialize(document) or {}
    vehicle["violations"] = serialize_many(violations)
    vehicle["challans"] = serialize_many(challans)
    return vehicle


@router.put("/{plate_number}")
async def update_vehicle(
    plate_number: str, body: VehicleBody, user: dict = Depends(get_current_user)
) -> dict:
    plate = plate_number.strip().upper()
    document = await coll(VEHICLES).find_one({"plate_number": plate})
    if not document:
        raise HTTPException(status_code=404, detail=f"{plate} is not in the register")

    changes = body.model_dump()
    changes["plate_number"] = plate
    changes["owner_phone"] = normalise_phone(body.owner_phone)
    changes["updated_at"] = utcnow_iso()
    changes["updated_by"] = user["user_id"]
    await coll(VEHICLES).update_one({"_id": document["_id"]}, {"$set": changes})

    # keep pending challans reachable by SMS after owner details are filled in
    await coll(CHALLANS).update_many(
        {"plate_number": plate, "status": "PENDING"},
        {
            "$set": {
                "owner_name": changes.get("owner_name", ""),
                "owner_phone": changes.get("owner_phone", ""),
            }
        },
    )
    return {"updated": True, "vehicle": serialize(await coll(VEHICLES).find_one({"_id": document["_id"]}))}


@router.delete("/{plate_number}")
async def delete_vehicle(plate_number: str, _: dict = Depends(require_admin)) -> dict:
    plate = plate_number.strip().upper()
    outcome = await coll(VEHICLES).delete_one({"plate_number": plate})
    if not outcome.deleted_count:
        raise HTTPException(status_code=404, detail=f"{plate} is not in the register")
    return {"deleted": True, "plate_number": plate}
