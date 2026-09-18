"""Maintenance alerts raised by the camera health monitor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..constants import ALERT_ACKNOWLEDGED, ALERT_OPEN, ALERT_RESOLVED
from ..database import ALERTS, coll
from ..deps import get_current_user, require_admin
from ..utils import serialize, serialize_many, utcnow_iso

router = APIRouter(prefix="/api/alerts", tags=["Maintenance Alerts"])


@router.get("")
async def list_alerts(
    alert_status: str | None = Query(default=None, alias="status"),
    camera_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(get_current_user),
) -> dict:
    query: dict = {}
    if alert_status:
        query["status"] = alert_status
    if camera_id:
        query["camera_id"] = camera_id

    documents = (
        await coll(ALERTS).find(query).sort("created_at", -1).limit(limit).to_list(limit)
    )
    everything = await coll(ALERTS).find({}).to_list(1000)
    return {
        "alerts": serialize_many(documents),
        "summary": {
            "open": sum(1 for item in everything if item.get("status") == ALERT_OPEN),
            "acknowledged": sum(
                1 for item in everything if item.get("status") == ALERT_ACKNOWLEDGED
            ),
            "resolved": sum(1 for item in everything if item.get("status") == ALERT_RESOLVED),
            "total": len(everything),
        },
    }


@router.post("/{alert_id}/acknowledge")
async def acknowledge(alert_id: str, user: dict = Depends(get_current_user)) -> dict:
    document = await coll(ALERTS).find_one({"_id": alert_id})
    if not document:
        raise HTTPException(status_code=404, detail="Alert not found")
    await coll(ALERTS).update_one(
        {"_id": alert_id},
        {
            "$set": {
                "status": ALERT_ACKNOWLEDGED,
                "acknowledged_by": user["user_id"],
                "acknowledged_at": utcnow_iso(),
            }
        },
    )
    return {"updated": True, "alert": serialize(await coll(ALERTS).find_one({"_id": alert_id}))}


@router.post("/{alert_id}/resolve")
async def resolve(
    alert_id: str, note: str = "", user: dict = Depends(get_current_user)
) -> dict:
    document = await coll(ALERTS).find_one({"_id": alert_id})
    if not document:
        raise HTTPException(status_code=404, detail="Alert not found")
    await coll(ALERTS).update_one(
        {"_id": alert_id},
        {
            "$set": {
                "status": ALERT_RESOLVED,
                "resolved_by": user["user_id"],
                "resolved_at": utcnow_iso(),
                "resolution": note or "Marked resolved by operator",
            }
        },
    )
    return {"updated": True, "alert": serialize(await coll(ALERTS).find_one({"_id": alert_id}))}


@router.delete("/clear-resolved")
async def clear_resolved(_: dict = Depends(require_admin)) -> dict:
    outcome = await coll(ALERTS).delete_many({"status": ALERT_RESOLVED})
    return {"deleted": outcome.deleted_count}
