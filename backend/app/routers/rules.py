"""Violation rules: fine amounts, confidence thresholds, auto-challan switches."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..constants import VIOLATION_TYPES
from ..database import RULES, coll
from ..deps import get_current_user, require_admin
from ..schemas import RuleBody
from ..services.rules_service import ensure_rules, list_rules
from ..utils import serialize, utcnow_iso

router = APIRouter(prefix="/api/rules", tags=["Violation Rules"])


@router.get("")
async def get_rules(_: dict = Depends(get_current_user)) -> dict:
    await ensure_rules()
    return {"rules": await list_rules(), "violation_types": VIOLATION_TYPES}


@router.put("/{code}")
async def update_rule(code: str, body: RuleBody, admin: dict = Depends(require_admin)) -> dict:
    code = code.upper()
    document = await coll(RULES).find_one({"code": code})
    if not document:
        raise HTTPException(status_code=404, detail=f"No rule for '{code}'")

    changes = {
        key: value
        for key, value in body.model_dump().items()
        if value is not None and key != "code"
    }
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "fine_amount" in changes and float(changes["fine_amount"]) < 0:
        raise HTTPException(status_code=400, detail="Fine amount cannot be negative")

    changes["updated_at"] = utcnow_iso()
    changes["updated_by"] = admin["user_id"]
    await coll(RULES).update_one({"_id": document["_id"]}, {"$set": changes})
    return {
        "updated": True,
        "rule": serialize(await coll(RULES).find_one({"_id": document["_id"]})),
    }


@router.post("/reset-defaults")
async def reset_defaults(_: dict = Depends(require_admin)) -> dict:
    documents = await coll(RULES).find({}).to_list(50)
    for document in documents:
        await coll(RULES).update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "fine_amount": float(document.get("default_fine") or 500),
                    "enabled": True,
                    "auto_challan": True,
                    "min_confidence": 0.6,
                    "updated_at": utcnow_iso(),
                }
            },
        )
    return {"reset": True, "rules": await list_rules()}
