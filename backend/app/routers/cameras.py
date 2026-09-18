"""Camera management, live MJPEG streaming and demo media handling."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response, StreamingResponse

from ..config import DEMO_DIR, UPLOAD_DIR
from ..constants import (
    DEMO_SOURCE_IMAGE,
    DEMO_SOURCE_VIDEO,
    MODE_DEMO,
    MODE_LIVE,
    STATUS_CONNECTING,
    STATUS_DISABLED,
)
from ..database import CAMERAS, USERS, coll
from ..deps import get_current_user, require_admin
from ..schemas import CameraCreate, CameraToggle, CameraUpdate
from ..security import decode_access_token
from ..services.camera_manager import (
    camera_manager,
    redact_url,
    resolve_source,
    test_camera_connection,
)
from ..services.detection_service import reset_camera_state
from ..services.pipeline import pipeline
from ..utils import serialize, utcnow_iso

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_UPLOAD_BYTES = 80 * 1024 * 1024


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def public_camera(document: dict, health: dict | None = None) -> dict:
    camera = serialize(document) or {}
    camera.pop("password", None)
    camera["password_set"] = bool(document.get("password"))
    kind, target = resolve_source(document)
    camera["source_kind"] = kind
    camera["stream_source"] = redact_url(target) if kind == "live" else Path(target).name
    camera["health"] = health or {
        "status": document.get("status") or STATUS_DISABLED,
        "online": False,
        "fps": document.get("fps") or 0,
        "last_seen": document.get("last_seen"),
        "last_frame_at": document.get("last_frame_at"),
        "connection_error": document.get("connection_error", ""),
        "violation_count": document.get("violation_count", 0),
        "thread_alive": False,
    }
    return camera


async def _load(camera_id: str) -> dict:
    document = await coll(CAMERAS).find_one({"camera_id": camera_id})
    if not document:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
    return document


async def _stream_user(token: str | None, request: Request) -> dict:
    """``<img src>`` cannot send headers, so the stream accepts ?token=."""
    raw = token
    if not raw:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            raw = header[7:]
    payload = decode_access_token(raw or "")
    if not payload:
        raise HTTPException(status_code=401, detail="A valid token is required for the stream")
    document = await coll(USERS).find_one({"user_id": payload.get("sub")})
    if not document or not document.get("active", True):
        raise HTTPException(status_code=401, detail="Account unavailable")
    return document


# --------------------------------------------------------------------------- #
# collection level
# --------------------------------------------------------------------------- #
@router.get("")
async def list_cameras(_: dict = Depends(get_current_user)) -> dict:
    documents = await coll(CAMERAS).find({}).to_list(200)
    documents.sort(key=lambda item: str(item.get("camera_id")))
    health_by_id = {item["camera_id"]: item for item in camera_manager.health_all()}
    cameras = [
        public_camera(document, health_by_id.get(str(document.get("camera_id"))))
        for document in documents
    ]
    online = sum(1 for camera in cameras if camera["health"].get("online"))
    return {
        "cameras": cameras,
        "summary": {
            "total": len(cameras),
            "enabled": sum(1 for camera in cameras if camera.get("enabled")),
            "online": online,
            "offline": len(cameras) - online,
            "live_mode": sum(1 for camera in cameras if camera.get("mode") == MODE_LIVE),
            "demo_mode": sum(1 for camera in cameras if camera.get("mode") == MODE_DEMO),
        },
    }


@router.get("/health/all")
async def cameras_health(_: dict = Depends(get_current_user)) -> dict:
    return {
        "cameras": camera_manager.health_all(),
        "summary": camera_manager.summary(),
        "pipeline": pipeline.status(),
    }


@router.get("/demo-media")
async def list_demo_media(_: dict = Depends(get_current_user)) -> dict:
    def describe(path: Path) -> dict:
        return {
            "name": path.name,
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "kind": "VIDEO" if path.suffix.lower() in VIDEO_SUFFIXES else "IMAGE",
        }

    files: list[dict] = []
    for directory in (DEMO_DIR, UPLOAD_DIR):
        for path in sorted(directory.glob("*")):
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES | IMAGE_SUFFIXES:
                files.append(describe(path))

    return {
        "files": files,
        "synthetic_available": True,
        "note": (
            "SYNTHETIC needs no file - the backend renders an animated traffic scene. "
            "Upload a traffic video or image to use VIDEO / IMAGE demo mode."
        ),
    }


@router.post("/upload-demo-media")
async def upload_demo_media(
    file: UploadFile = File(...), _: dict = Depends(require_admin)
) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in VIDEO_SUFFIXES | IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: "
            f"{', '.join(sorted(VIDEO_SUFFIXES | IMAGE_SUFFIXES))}",
        )

    safe_name = Path(file.filename or "upload").name.replace(" ", "_")
    destination = UPLOAD_DIR / f"{utcnow_iso().replace(':', '-')}_{safe_name}"
    size = 0
    with destination.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                handle.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File larger than 80 MB")
            handle.write(chunk)

    return {
        "uploaded": True,
        "name": destination.name,
        "path": str(destination),
        "kind": "VIDEO" if suffix in VIDEO_SUFFIXES else "IMAGE",
        "size_mb": round(size / (1024 * 1024), 2),
        "message": "Select this file as the DEMO source of a camera.",
    }


@router.post("/test-config")
async def test_configuration(body: CameraCreate, _: dict = Depends(require_admin)) -> dict:
    outcome = await asyncio.to_thread(test_camera_connection, body.model_dump())
    return outcome


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_camera(body: CameraCreate, admin: dict = Depends(require_admin)) -> dict:
    camera_id = body.camera_id.strip().upper()
    if await coll(CAMERAS).find_one({"camera_id": camera_id}):
        raise HTTPException(status_code=409, detail=f"Camera ID '{camera_id}' already exists")

    if body.mode == MODE_LIVE and not (body.rtsp_url.strip() or body.ip_address.strip()):
        raise HTTPException(
            status_code=400,
            detail="LIVE mode needs an RTSP URL or an IP address.",
        )
    if body.mode == MODE_DEMO and body.demo_source_type in {
        DEMO_SOURCE_VIDEO,
        DEMO_SOURCE_IMAGE,
    }:
        if not body.demo_source_path or not Path(body.demo_source_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Select an uploaded video/image file for this demo source.",
            )

    document = {
        **body.model_dump(),
        "camera_id": camera_id,
        "status": STATUS_CONNECTING,
        "fps": 0.0,
        "resolution": "",
        "violation_count": 0,
        "frames_captured": 0,
        "reconnect_attempts": 0,
        "last_seen": None,
        "last_frame_at": None,
        "offline_since": None,
        "connection_error": "",
        "created_at": utcnow_iso(),
        "created_by": admin["user_id"],
        "updated_at": utcnow_iso(),
    }
    inserted = await coll(CAMERAS).insert_one(document)
    document["_id"] = inserted.inserted_id

    camera_manager.restart(document)
    return {"created": True, "camera": public_camera(document)}


# --------------------------------------------------------------------------- #
# item level
# --------------------------------------------------------------------------- #
@router.get("/{camera_id}")
async def get_camera(camera_id: str, _: dict = Depends(get_current_user)) -> dict:
    document = await _load(camera_id)
    worker = camera_manager.get(camera_id)
    return public_camera(document, worker.health() if worker else None)


@router.put("/{camera_id}")
async def update_camera(
    camera_id: str, body: CameraUpdate, admin: dict = Depends(require_admin)
) -> dict:
    document = await _load(camera_id)
    changes = {key: value for key, value in body.model_dump().items() if value is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    changes["updated_at"] = utcnow_iso()
    changes["updated_by"] = admin["user_id"]
    await coll(CAMERAS).update_one({"_id": document["_id"]}, {"$set": changes})

    updated = await _load(camera_id)
    reset_camera_state(camera_id)
    camera_manager.restart(updated)
    return {"updated": True, "camera": public_camera(updated)}


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str, _: dict = Depends(require_admin)) -> dict:
    document = await _load(camera_id)
    camera_manager.stop_camera(camera_id)
    await coll(CAMERAS).delete_one({"_id": document["_id"]})
    return {"deleted": True, "camera_id": camera_id}


@router.post("/{camera_id}/toggle")
async def toggle_camera(
    camera_id: str, body: CameraToggle, admin: dict = Depends(require_admin)
) -> dict:
    document = await _load(camera_id)
    await coll(CAMERAS).update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                "enabled": body.enabled,
                "status": STATUS_CONNECTING if body.enabled else STATUS_DISABLED,
                "updated_at": utcnow_iso(),
                "updated_by": admin["user_id"],
            }
        },
    )
    updated = await _load(camera_id)
    if body.enabled:
        camera_manager.restart(updated)
    else:
        camera_manager.stop_camera(camera_id)
    return {"updated": True, "enabled": body.enabled, "camera": public_camera(updated)}


@router.post("/{camera_id}/test")
async def test_camera(camera_id: str, _: dict = Depends(get_current_user)) -> dict:
    document = await _load(camera_id)
    return await asyncio.to_thread(test_camera_connection, document)


@router.post("/{camera_id}/restart")
async def restart_camera(camera_id: str, _: dict = Depends(require_admin)) -> dict:
    document = await _load(camera_id)
    reset_camera_state(camera_id)
    camera_manager.restart(document)
    return {"restarted": True, "camera_id": camera_id}


@router.post("/{camera_id}/detect-now")
async def detect_now(camera_id: str, _: dict = Depends(get_current_user)) -> dict:
    """Run one detection pass on this camera immediately (demo friendly)."""
    document = await _load(camera_id)
    worker = camera_manager.get(camera_id)
    if worker is None:
        raise HTTPException(status_code=409, detail="Camera is not running")

    stored = await pipeline.process_camera_once(document)
    return {
        "camera_id": camera_id,
        "violations_recorded": stored,
        "message": (
            f"{stored} violation(s) recorded."
            if stored
            else "No violation detected in the current frame (or cooldown active)."
        ),
    }


# --------------------------------------------------------------------------- #
# streaming
# --------------------------------------------------------------------------- #
@router.get("/{camera_id}/snapshot")
async def snapshot(
    camera_id: str,
    request: Request,
    token: str | None = Query(default=None),
) -> Response:
    await _stream_user(token, request)
    worker = camera_manager.get(camera_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Camera is not running")
    frame = worker.snapshot_jpeg()
    if not frame:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(content=frame, media_type="image/jpeg")


@router.get("/{camera_id}/stream")
async def stream(
    camera_id: str,
    request: Request,
    token: str | None = Query(default=None),
    fps: float = Query(default=8.0, ge=1, le=25),
) -> StreamingResponse:
    """MJPEG stream for one camera; each camera is streamed independently."""
    await _stream_user(token, request)

    async def frames():
        interval = 1.0 / fps
        last_sent: bytes | None = None
        while True:
            if await request.is_disconnected():
                break
            worker = camera_manager.get(camera_id)
            payload = worker.snapshot_jpeg() if worker else None
            if payload and payload is not last_sent:
                last_sent = payload
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(payload)).encode()
                    + b"\r\n\r\n"
                    + payload
                    + b"\r\n"
                )
            await asyncio.sleep(interval)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Camera-Id": camera_id},
    )
