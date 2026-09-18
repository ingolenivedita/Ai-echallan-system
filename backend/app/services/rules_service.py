"""Violation rule catalogue (fine amounts, thresholds, auto-challan switches)."""

from __future__ import annotations

from ..constants import VIOLATION_CATALOGUE
from ..database import RULES, coll
from ..utils import serialize_many, utcnow_iso


async def ensure_rules() -> None:
    """Seed the four tracked violations if the collection is empty."""
    for entry in VIOLATION_CATALOGUE:
        existing = await coll(RULES).find_one({"code": entry["code"]})
        if existing:
            continue
        await coll(RULES).insert_one(
            {
                "code": entry["code"],
                "label": entry["label"],
                "section": entry["section"],
                "description": entry["description"],
                "severity": entry["severity"],
                "fine_amount": float(entry["default_fine"]),
                "default_fine": float(entry["default_fine"]),
                "min_confidence": 0.6,
                "auto_challan": True,
                "enabled": True,
                "created_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
            }
        )


async def list_rules() -> list[dict]:
    documents = await coll(RULES).find({}).to_list(100)
    order = {entry["code"]: index for index, entry in enumerate(VIOLATION_CATALOGUE)}
    documents.sort(key=lambda item: order.get(item.get("code"), 99))
    return serialize_many(documents)


async def get_rule(code: str) -> dict:
    document = await coll(RULES).find_one({"code": code})
    if document:
        return document
    fallback = next(
        (entry for entry in VIOLATION_CATALOGUE if entry["code"] == code),
        {"code": code, "label": code, "default_fine": 500, "section": "", "severity": "medium"},
    )
    return {
        "code": code,
        "label": fallback.get("label", code),
        "section": fallback.get("section", ""),
        "fine_amount": float(fallback.get("default_fine", 500)),
        "min_confidence": 0.6,
        "auto_challan": True,
        "enabled": True,
    }


async def rules_map() -> dict[str, dict]:
    documents = await coll(RULES).find({}).to_list(100)
    return {document["code"]: document for document in documents if document.get("code")}
