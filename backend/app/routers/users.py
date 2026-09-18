"""User administration (Admin and Traffic Officer accounts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..constants import ROLE_LABELS, ROLES
from ..database import AUDIT, USERS, coll
from ..deps import get_current_user, require_admin
from ..schemas import UserCreate, UserUpdate
from ..security import hash_password
from ..services.sms_service import normalise_phone
from ..utils import serialize, utcnow_iso

router = APIRouter(prefix="/api/users", tags=["Users"])


def public(document: dict) -> dict:
    user = serialize(document) or {}
    user.pop("password_hash", None)
    user.pop("demo_password", None)
    user["role_label"] = ROLE_LABELS.get(user.get("role", ""), user.get("role", ""))
    return user


@router.get("")
async def list_users(_: dict = Depends(require_admin)) -> dict:
    documents = await coll(USERS).find({}).sort("user_id", 1).to_list(200)
    users = [public(document) for document in documents]
    return {
        "users": users,
        "summary": {
            "total": len(users),
            "admins": sum(1 for user in users if user.get("role") == "admin"),
            "officers": sum(1 for user in users if user.get("role") == "officer"),
            "active": sum(1 for user in users if user.get("active")),
        },
        "roles": [{"value": role, "label": ROLE_LABELS[role]} for role in ROLES],
    }


@router.post("")
async def create_user(body: UserCreate, admin: dict = Depends(require_admin)) -> dict:
    user_id = body.user_id.strip()
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(ROLES)}")
    if await coll(USERS).find_one({"user_id": user_id}):
        raise HTTPException(status_code=409, detail=f"User ID '{user_id}' already exists")

    document = {
        "user_id": user_id,
        "name": body.name.strip(),
        "role": body.role,
        "designation": body.designation,
        "phone": normalise_phone(body.phone),
        "email": body.email.strip(),
        "station": body.station,
        "active": body.active,
        "password_hash": hash_password(body.password),
        "is_demo": False,
        "login_count": 0,
        "last_login_at": None,
        "created_at": utcnow_iso(),
        "created_by": admin["user_id"],
        "updated_at": utcnow_iso(),
    }
    inserted = await coll(USERS).insert_one(document)
    document["_id"] = inserted.inserted_id
    await coll(AUDIT).insert_one(
        {
            "action": "USER_CREATED",
            "actor": admin["user_id"],
            "detail": f"Created {user_id} ({body.role})",
            "created_at": utcnow_iso(),
        }
    )
    return {"created": True, "user": public(document)}


@router.put("/{user_id}")
async def update_user(
    user_id: str, body: UserUpdate, admin: dict = Depends(require_admin)
) -> dict:
    document = await coll(USERS).find_one({"user_id": user_id})
    if not document:
        raise HTTPException(status_code=404, detail="User not found")

    changes = {key: value for key, value in body.model_dump().items() if value is not None}
    password = changes.pop("password", None)
    if password:
        changes["password_hash"] = hash_password(password)
    if "role" in changes and changes["role"] not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(ROLES)}")
    if "phone" in changes:
        changes["phone"] = normalise_phone(changes["phone"])
    if (
        changes.get("active") is False
        and document.get("user_id") == admin["user_id"]
    ):
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    changes["updated_at"] = utcnow_iso()
    changes["updated_by"] = admin["user_id"]
    await coll(USERS).update_one({"_id": document["_id"]}, {"$set": changes})
    return {"updated": True, "user": public(await coll(USERS).find_one({"_id": document["_id"]}))}


@router.delete("/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)) -> dict:
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    document = await coll(USERS).find_one({"user_id": user_id})
    if not document:
        raise HTTPException(status_code=404, detail="User not found")

    admins = await coll(USERS).count_documents({"role": "admin", "active": True})
    if document.get("role") == "admin" and admins <= 1:
        raise HTTPException(status_code=400, detail="At least one administrator must remain")

    await coll(USERS).delete_one({"_id": document["_id"]})
    await coll(AUDIT).insert_one(
        {
            "action": "USER_DELETED",
            "actor": admin["user_id"],
            "detail": f"Deleted {user_id}",
            "created_at": utcnow_iso(),
        }
    )
    return {"deleted": True, "user_id": user_id}


@router.get("/audit/log")
async def audit_log(limit: int = 100, _: dict = Depends(require_admin)) -> dict:
    documents = (
        await coll(AUDIT).find({}).sort("created_at", -1).limit(min(limit, 500)).to_list(500)
    )
    return {"entries": [serialize(document) for document in documents]}
