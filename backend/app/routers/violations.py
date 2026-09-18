"""Violation records: listing, review, evidence images and manual analysis."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse

from ..config import EVIDENCE_DIR
from ..constants import (
    VIOLATION_APPROVED,
    VIOLATION_CHALLANED,
    VIOLATION_LABELS,
    VIOLATION_PENDING,
    VIOLATION_REJECTED,
    VIOLATION_TYPES,
)
from ..database import CAMERAS, VIOLATIONS, coll
from ..deps import get_current_user, require_admin
from ..schemas import ManualViolationBody, ViolationReviewBody
from ..security import decode_access_token
from ..services import anpr_service, detection_service
from ..services.challan_service import issue_challan
from ..utils import day_start_iso, serialize, serialize_many, utcnow_iso

router = APIRouter(prefix="/api/violations", tags=["Violations"])


def _query(
    camera_id: str | None,
    violation_type: str | None,
    review_status: str | None,
    plate: str | None,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    query: dict = {}
    if camera_id:
        query["camera_id"] = camera_id
    if violation_type:
        query["violation_type"] = violation_type
    if review_status:
        query["status"] = review_status
    if plate:
        query["plate_number"] = {"$regex": plate.upper(), "$options": "i"}
    if date_from or date_to:
        window: dict = {}
        if date_from:
            window["$gte"] = f"{date_from}T00:00:00"
        if date_to:
            window["$lte"] = f"{date_to}T23:59:59"
        query["detected_at"] = window
    return query


# --------------------------------------------------------------------------- #
@router.get("")
async def list_violations(
    camera_id: str | None = None,
    violation_type: str | None = None,
    review_status: str | None = Query(default=None, alias="status"),
    plate: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    _: dict = Depends(get_current_user),
) -> dict:
    query = _query(camera_id, violation_type, review_status, plate, date_from, date_to)
    total = await coll(VIOLATIONS).count_documents(query)
    documents = (
        await coll(VIOLATIONS)
        .find(query)
        .sort("detected_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "violations": serialize_many(documents),
        "page": page,
        "limit": limit,
        "total": total,
        "pages": max((total + limit - 1) // limit, 1),
    }


@router.get("/stats")
async def violation_stats(_: dict = Depends(get_current_user)) -> dict:
    documents = await coll(VIOLATIONS).find({}).to_list(20000)
    today = day_start_iso()

    by_type: dict[str, int] = {code: 0 for code in VIOLATION_TYPES}
    by_camera: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_detector: dict[str, int] = {}

    for document in documents:
        by_type[document.get("violation_type", "")] = (
            by_type.get(document.get("violation_type", ""), 0) + 1
        )
        by_camera[document.get("camera_id", "")] = (
            by_camera.get(document.get("camera_id", ""), 0) + 1
        )
        by_status[document.get("status", "")] = by_status.get(document.get("status", ""), 0) + 1
        by_detector[document.get("detector", "")] = (
            by_detector.get(document.get("detector", ""), 0) + 1
        )

    return {
        "total": len(documents),
        "today": sum(1 for item in documents if (item.get("detected_at") or "") >= today),
        "pending_review": by_status.get(VIOLATION_PENDING, 0),
        "by_type": [
            {"code": code, "label": VIOLATION_LABELS.get(code, code), "count": count}
            for code, count in by_type.items()
        ],
        "by_camera": [
            {"camera_id": camera, "count": count} for camera, count in sorted(by_camera.items())
        ],
        "by_status": by_status,
        "by_detector": by_detector,
    }


@router.get("/evidence/{filename}")
async def evidence_image(
    filename: str, request: Request, token: str | None = Query(default=None)
) -> FileResponse:
    raw = token
    if not raw:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            raw = header[7:]
    if not decode_access_token(raw or ""):
        raise HTTPException(status_code=401, detail="A valid token is required")

    safe_name = Path(filename).name
    path = EVIDENCE_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence image not found")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/analyze-upload")
async def analyze_upload(
    file: UploadFile = File(...),
    camera_id: str = Form(default=""),
    record: bool = Form(default=False),
    detector: str = Form(default="auto"),
    user: dict = Depends(get_current_user),
) -> dict:
    """Run the detection service on an uploaded image (Violations page tool)."""
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file")

    frame = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode this image")

    camera = await coll(CAMERAS).find_one({"camera_id": camera_id}) if camera_id else None
    camera = camera or {
        "camera_id": camera_id or "UPLOAD",
        "name": "Manual upload",
        "location": "Uploaded evidence",
        "mode": "DEMO",
        "demo_source_type": "IMAGE",
        "allowed_direction": "ANY",
    }

    outcome = await detection_service.analyse(camera, frame, {}, preference=detector)
    anpr = await anpr_service.read_plate(payload, camera.get("camera_id", "UPLOAD"))
    plate_number = (anpr.get("data", {}).get("plate_number") or "").upper()
    plate_source = anpr.get("data", {}).get("plate_source", "")

    evidence = ""
    recorded: list[dict] = []
    if outcome["detections"]:
        evidence = detection_service.save_evidence(frame, outcome["detections"], camera)

    if record and outcome["detections"]:
        for detection in outcome["detections"]:
            document = {
                "camera_id": camera.get("camera_id", "UPLOAD"),
                "camera_name": camera.get("name", ""),
                "location": camera.get("location", ""),
                "violation_type": detection["violation_type"],
                "violation_label": VIOLATION_LABELS.get(
                    detection["violation_type"], detection["violation_type"]
                ),
                "confidence": detection["confidence"],
                "detector": outcome.get("detector", ""),
                "simulated": bool(outcome.get("simulated")),
                "reason": detection.get("reason", ""),
                "box": detection.get("box"),
                "scene": outcome.get("scene", ""),
                "plate_number": plate_number,
                "plate_source": plate_source,
                "vehicle_type": detection.get("vehicle_type", ""),
                "evidence_image": evidence,
                "detected_at": utcnow_iso(),
                "status": VIOLATION_PENDING,
                "source": "MANUAL_UPLOAD",
                "reviewed_by": "",
                "created_by": user["user_id"],
                "created_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
            }
            inserted = await coll(VIOLATIONS).insert_one(document)
            document["_id"] = inserted.inserted_id
            recorded.append(serialize(document))

    return {
        "detector": outcome.get("detector"),
        "simulated": outcome.get("simulated"),
        "notes": outcome.get("notes"),
        "scene": outcome.get("scene"),
        "detections": outcome["detections"],
        "evidence_image": evidence,
        "anpr": {
            "plate_number": plate_number,
            "plate_source": plate_source,
            "configured": anpr["configured"],
            "message": anpr["message"],
        },
        "recorded": recorded,
    }


@router.post("/manual")
async def create_manual_violation(
    body: ManualViolationBody, user: dict = Depends(get_current_user)
) -> dict:
    if body.violation_type not in VIOLATION_TYPES:
        raise HTTPException(status_code=400, detail="Unknown violation type")

    camera = await coll(CAMERAS).find_one({"camera_id": body.camera_id})
    document = {
        "camera_id": body.camera_id,
        "camera_name": (camera or {}).get("name", ""),
        "location": (camera or {}).get("location", ""),
        "violation_type": body.violation_type,
        "violation_label": VIOLATION_LABELS.get(body.violation_type, body.violation_type),
        "confidence": min(max(body.confidence, 0.0), 1.0),
        "detector": "OFFICER_MANUAL",
        "simulated": False,
        "reason": body.remarks or "Recorded manually by officer",
        "plate_number": body.plate_number.upper(),
        "plate_source": "MANUAL" if body.plate_number else "",
        "evidence_image": "",
        "detected_at": utcnow_iso(),
        "status": VIOLATION_APPROVED,
        "source": "MANUAL_ENTRY",
        "reviewed_by": user["user_id"],
        "reviewed_at": utcnow_iso(),
        "created_by": user["user_id"],
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }
    inserted = await coll(VIOLATIONS).insert_one(document)
    document["_id"] = inserted.inserted_id
    return {"created": True, "violation": serialize(document)}


# --------------------------------------------------------------------------- #
@router.get("/{violation_id}")
async def get_violation(violation_id: str, _: dict = Depends(get_current_user)) -> dict:
    document = await coll(VIOLATIONS).find_one({"_id": violation_id})
    if not document:
        raise HTTPException(status_code=404, detail="Violation not found")
    return serialize(document)


@router.post("/{violation_id}/review")
async def review_violation(
    violation_id: str,
    body: ViolationReviewBody,
    issue: bool = Query(default=False, description="Issue a challan on approval"),
    user: dict = Depends(get_current_user),
) -> dict:
    if body.status not in {VIOLATION_APPROVED, VIOLATION_REJECTED}:
        raise HTTPException(
            status_code=400,
            detail=f"status must be {VIOLATION_APPROVED} or {VIOLATION_REJECTED}",
        )

    document = await coll(VIOLATIONS).find_one({"_id": violation_id})
    if not document:
        raise HTTPException(status_code=404, detail="Violation not found")
    if document.get("status") == VIOLATION_CHALLANED:
        raise HTTPException(
            status_code=409, detail="A challan was already issued for this violation"
        )

    changes = {
        "status": body.status,
        "remarks": body.remarks,
        "reviewed_by": user["user_id"],
        "reviewed_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }
    if body.plate_number:
        changes["plate_number"] = body.plate_number.upper()
        changes["plate_source"] = "OFFICER_CORRECTED"

    await coll(VIOLATIONS).update_one({"_id": violation_id}, {"$set": changes})
    updated = await coll(VIOLATIONS).find_one({"_id": violation_id})

    challan_result = None
    if body.status == VIOLATION_APPROVED and issue:
        if not (updated or {}).get("plate_number"):
            raise HTTPException(
                status_code=400,
                detail="A number plate is required before a challan can be issued.",
            )
        challan_result = await issue_challan(updated or {}, actor=user["user_id"])
        updated = await coll(VIOLATIONS).find_one({"_id": violation_id})

    return {
        "updated": True,
        "violation": serialize(updated),
        "challan": challan_result,
    }


@router.delete("/{violation_id}")
async def delete_violation(violation_id: str, _: dict = Depends(require_admin)) -> dict:
    document = await coll(VIOLATIONS).find_one({"_id": violation_id})
    if not document:
        raise HTTPException(status_code=404, detail="Violation not found")
    if document.get("evidence_image"):
        (EVIDENCE_DIR / Path(document["evidence_image"]).name).unlink(missing_ok=True)
    await coll(VIOLATIONS).delete_one({"_id": violation_id})
    return {"deleted": True, "id": violation_id}
