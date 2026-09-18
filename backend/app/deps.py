"""FastAPI dependencies: authentication and role based access control."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .constants import ROLE_ADMIN
from .database import USERS, coll
from .security import decode_access_token
from .utils import serialize

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated or session expired",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_ERROR

    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise CREDENTIALS_ERROR

    document = await coll(USERS).find_one({"user_id": payload["sub"]})
    if not document or not document.get("active", True):
        raise CREDENTIALS_ERROR

    user = serialize(document) or {}
    user.pop("password_hash", None)
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an Administrator account",
        )
    return user
