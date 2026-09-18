"""Reports: aggregated statistics, CSV export and an AI written summary."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..constants import CHALLAN_PAID, CHALLAN_PENDING, VIOLATION_LABELS, VIOLATION_TYPES
from ..database import CAMERAS, CHALLANS, VEHICLES, VIOLATIONS, coll
from ..deps import get_current_user
from ..services import ai_service
from ..utils import day_key, iso, percentage, utcnow, utcnow_iso

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _window(date_from: str | None, date_to: str | None, days: int) -> tuple[str, str]:
    if date_from and date_to:
        return f"{date_from}T00:00:00", f"{date_to}T23:59:59"
    start = iso(utcnow() - timedelta(days=days - 1))[:10]
    return f"{start}T00:00:00", f"{iso(utcnow())[:10]}T23:59:59"


async def _collect(date_from: str | None, date_to: str | None, days: int) -> dict:
    start, end = _window(date_from, date_to, days)
    violations = [
        item
        for item in await coll(VIOLATIONS).find({}).to_list(30000)
        if start <= (item.get("detected_at") or "") <= end
    ]
    challans = [
        item
        for item in await coll(CHALLANS).find({}).to_list(30000)
        if start <= (item.get("issued_at") or "") <= end
    ]
    return {"start": start, "end": end, "violations": violations, "challans": challans}


@router.get("/overview")
async def overview(
    date_from: str | None = None,
    date_to: str | None = None,
    days: int = Query(default=7, ge=1, le=90),
    _: dict = Depends(get_current_user),
) -> dict:
    data = await _collect(date_from, date_to, days)
    violations, challans = data["violations"], data["challans"]
    cameras = await coll(CAMERAS).find({}).to_list(200)

    by_type = {code: {"violations": 0, "challans": 0, "amount": 0.0} for code in VIOLATION_TYPES}
    for item in violations:
        entry = by_type.setdefault(
            item.get("violation_type", ""), {"violations": 0, "challans": 0, "amount": 0.0}
        )
        entry["violations"] += 1
    for item in challans:
        entry = by_type.setdefault(
            item.get("violation_type", ""), {"violations": 0, "challans": 0, "amount": 0.0}
        )
        entry["challans"] += 1
        entry["amount"] += float(item.get("fine_amount") or 0)

    daily: dict[str, dict] = {}
    for item in violations:
        key = day_key(item.get("detected_at"))
        daily.setdefault(key, {"date": key, "violations": 0, "challans": 0, "amount": 0.0})
        daily[key]["violations"] += 1
    for item in challans:
        key = day_key(item.get("issued_at"))
        daily.setdefault(key, {"date": key, "violations": 0, "challans": 0, "amount": 0.0})
        daily[key]["challans"] += 1
        daily[key]["amount"] += float(item.get("fine_amount") or 0)

    by_camera = []
    for camera in sorted(cameras, key=lambda item: str(item.get("camera_id"))):
        camera_id = str(camera.get("camera_id"))
        camera_violations = [item for item in violations if item.get("camera_id") == camera_id]
        camera_challans = [item for item in challans if item.get("camera_id") == camera_id]
        by_camera.append(
            {
                "camera_id": camera_id,
                "name": camera.get("name", ""),
                "location": camera.get("location", ""),
                "mode": camera.get("mode", ""),
                "violations": len(camera_violations),
                "challans": len(camera_challans),
                "amount": round(
                    sum(float(item.get("fine_amount") or 0) for item in camera_challans), 2
                ),
            }
        )

    repeat: dict[str, dict] = {}
    for item in challans:
        plate = item.get("plate_number") or "UNKNOWN"
        entry = repeat.setdefault(plate, {"plate_number": plate, "challans": 0, "amount": 0.0})
        entry["challans"] += 1
        entry["amount"] += float(item.get("fine_amount") or 0)
    top_offenders = sorted(repeat.values(), key=lambda item: item["challans"], reverse=True)[:10]

    paid = [item for item in challans if item.get("status") == CHALLAN_PAID]
    pending = [item for item in challans if item.get("status") == CHALLAN_PENDING]
    total_amount = sum(float(item.get("fine_amount") or 0) for item in challans)
    collected = sum(float(item.get("amount_paid") or item.get("fine_amount") or 0) for item in paid)

    detector_split: dict[str, int] = {}
    for item in violations:
        detector_split[item.get("detector", "UNKNOWN")] = (
            detector_split.get(item.get("detector", "UNKNOWN"), 0) + 1
        )

    return {
        "period": {"from": data["start"][:10], "to": data["end"][:10]},
        "totals": {
            "violations": len(violations),
            "challans": len(challans),
            "paid": len(paid),
            "pending": len(pending),
            "total_amount": round(total_amount, 2),
            "collected_amount": round(collected, 2),
            "pending_amount": round(
                sum(float(item.get("fine_amount") or 0) for item in pending), 2
            ),
            "collection_rate": percentage(collected, total_amount),
            "challan_conversion_rate": percentage(len(challans), len(violations)),
            "registered_vehicles": await coll(VEHICLES).count_documents({}),
        },
        "by_type": [
            {
                "code": code,
                "label": VIOLATION_LABELS.get(code, code),
                **values,
                "amount": round(values["amount"], 2),
            }
            for code, values in by_type.items()
        ],
        "by_camera": by_camera,
        "daily": sorted(daily.values(), key=lambda item: item["date"]),
        "top_offenders": top_offenders,
        "detector_split": detector_split,
        "generated_at": utcnow_iso(),
    }


def _csv_response(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/violations")
async def export_violations(
    date_from: str | None = None,
    date_to: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    _: dict = Depends(get_current_user),
) -> StreamingResponse:
    data = await _collect(date_from, date_to, days)
    return _csv_response(
        sorted(data["violations"], key=lambda item: item.get("detected_at") or ""),
        [
            "detected_at",
            "camera_id",
            "camera_name",
            "location",
            "violation_type",
            "violation_label",
            "confidence",
            "detector",
            "simulated",
            "plate_number",
            "plate_source",
            "status",
            "challan_number",
            "evidence_image",
        ],
        f"violations_{utcnow().strftime('%Y%m%d_%H%M')}.csv",
    )


@router.get("/export/challans")
async def export_challans(
    date_from: str | None = None,
    date_to: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    _: dict = Depends(get_current_user),
) -> StreamingResponse:
    data = await _collect(date_from, date_to, days)
    return _csv_response(
        sorted(data["challans"], key=lambda item: item.get("issued_at") or ""),
        [
            "challan_number",
            "issued_at",
            "camera_id",
            "location",
            "violation_label",
            "section",
            "plate_number",
            "owner_name",
            "owner_phone",
            "fine_amount",
            "status",
            "amount_paid",
            "paid_at",
            "due_date",
            "sms_status",
            "issued_by",
        ],
        f"challans_{utcnow().strftime('%Y%m%d_%H%M')}.csv",
    )


@router.post("/ai-summary")
async def ai_summary(
    date_from: str | None = None,
    date_to: str | None = None,
    days: int = Query(default=7, ge=1, le=90),
    _: dict = Depends(get_current_user),
) -> dict:
    report = await overview(date_from=date_from, date_to=date_to, days=days)  # type: ignore[arg-type]
    totals = report["totals"]
    lines = [
        f"Reporting period: {report['period']['from']} to {report['period']['to']}",
        f"Violations detected: {totals['violations']}",
        f"Challans issued: {totals['challans']} "
        f"(paid {totals['paid']}, pending {totals['pending']})",
        f"Total fine value: Rs.{totals['total_amount']}, "
        f"collected Rs.{totals['collected_amount']} ({totals['collection_rate']}%)",
        "Violations by type: "
        + ", ".join(f"{item['label']} {item['violations']}" for item in report["by_type"]),
        "Camera wise: "
        + ", ".join(
            f"{item['camera_id']} {item['violations']}" for item in report["by_camera"]
        ),
        "Detector split: "
        + ", ".join(f"{key} {value}" for key, value in report["detector_split"].items()),
    ]
    outcome = await ai_service.summarise(
        "Write a short enforcement briefing from these statistics:\n" + "\n".join(lines)
    )
    return {
        "configured": outcome["configured"],
        "ok": outcome["ok"],
        "message": outcome["message"],
        "summary": outcome["data"].get("summary", ""),
        "statistics_used": lines,
        "period": report["period"],
    }
