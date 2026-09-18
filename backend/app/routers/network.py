"""Network Status page.

Only things the backend can actually measure are reported: TCP reachability of
each camera, database connectivity, backend uptime and an outbound HTTP check.
Wi-Fi SSID / signal strength are deliberately reported as "not measurable" rather
than guessed.
"""

from __future__ import annotations

import asyncio
import platform
import socket
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends

from ..config import settings
from ..constants import MODE_LIVE
from ..database import CAMERAS, coll, database
from ..deps import get_current_user
from ..services.camera_manager import build_rtsp_url, camera_manager
from ..services.pipeline import pipeline
from ..utils import utcnow, utcnow_iso

router = APIRouter(prefix="/api/network", tags=["Network Status"])

BOOT_TIME = time.time()
INTERNET_PROBES = [
    ("Google", "https://www.gstatic.com/generate_204"),
    ("Groq API", "https://api.groq.com/openai/v1/models"),
]


async def _tcp_check(host: str, port: int, timeout: float = 3.0) -> dict:
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return {
            "reachable": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "detail": f"TCP connect to {host}:{port} succeeded",
        }
    except asyncio.TimeoutError:
        return {
            "reachable": False,
            "latency_ms": int(timeout * 1000),
            "detail": f"Timed out connecting to {host}:{port}",
        }
    except OSError as exc:
        return {
            "reachable": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "detail": f"{type(exc).__name__}: {exc}",
        }


def _host_port(camera: dict) -> tuple[str, int]:
    url = build_rtsp_url(camera)
    if url:
        parsed = urlparse(url)
        if parsed.hostname:
            return parsed.hostname, parsed.port or 554
    return (camera.get("ip_address") or "").strip(), 554


@router.get("/status")
async def network_status(_: dict = Depends(get_current_user)) -> dict:
    cameras = await coll(CAMERAS).find({}).to_list(200)
    health_by_id = {item["camera_id"]: item for item in camera_manager.health_all()}

    async def camera_entry(camera: dict) -> dict:
        camera_id = str(camera.get("camera_id"))
        health = health_by_id.get(camera_id, {})
        entry = {
            "camera_id": camera_id,
            "name": camera.get("name", ""),
            "location": camera.get("location", ""),
            "mode": camera.get("mode", "DEMO"),
            "ip_address": camera.get("ip_address", ""),
            "enabled": bool(camera.get("enabled", True)),
            "stream_status": health.get("status") or camera.get("status") or "UNKNOWN",
            "fps": health.get("fps", 0),
            "last_seen": health.get("last_seen") or camera.get("last_seen"),
            "last_frame_at": health.get("last_frame_at") or camera.get("last_frame_at"),
            "connection_error": health.get("connection_error")
            or camera.get("connection_error", ""),
        }

        if (camera.get("mode") or "DEMO").upper() != MODE_LIVE:
            entry["network_check"] = {
                "reachable": None,
                "latency_ms": None,
                "detail": "Demo source - no network path to test.",
            }
            return entry

        host, port = _host_port(camera)
        entry["network_check"] = (
            await _tcp_check(host, port)
            if host
            else {
                "reachable": False,
                "latency_ms": None,
                "detail": "No IP address or RTSP host configured.",
            }
        )
        entry["checked_endpoint"] = f"{host}:{port}" if host else ""
        return entry

    camera_results = await asyncio.gather(*(camera_entry(camera) for camera in cameras))

    async def probe(name: str, url: str) -> dict:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                response = await client.get(url)
            return {
                "name": name,
                "url": url,
                "reachable": True,
                "status_code": response.status_code,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except httpx.HTTPError as exc:
            return {
                "name": name,
                "url": url,
                "reachable": False,
                "status_code": None,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "detail": str(exc)[:160],
            }

    internet = await asyncio.gather(*(probe(name, url) for name, url in INTERNET_PROBES))
    db_health = await database.health()
    uptime_seconds = int(time.time() - BOOT_TIME)

    live_cameras = [item for item in camera_results if item["mode"] == MODE_LIVE]
    return {
        "backend": {
            "status": "ONLINE",
            "uptime_seconds": uptime_seconds,
            "uptime_human": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m",
            "environment": settings.app_env,
            "hostname": socket.gethostname(),
            "platform": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "pipeline": pipeline.status(),
        },
        "database": {
            "backend": db_health["backend"],
            "healthy": db_health["healthy"],
            "database_name": db_health["database_name"],
            "connected_at": db_health["connected_at"],
            "error": db_health["error"],
        },
        "cameras": camera_results,
        "camera_summary": {
            "total": len(camera_results),
            "streaming": sum(
                1 for item in camera_results if item["stream_status"] == "ONLINE"
            ),
            "live_mode": len(live_cameras),
            "live_reachable": sum(
                1 for item in live_cameras if item["network_check"].get("reachable")
            ),
        },
        "internet": {
            "reachable": any(item["reachable"] for item in internet),
            "probes": internet,
        },
        "not_measurable": [
            "Wi-Fi SSID, signal strength and link speed are not exposed to the backend "
            "process, so they are not reported here.",
            "Camera-side network quality can only be inferred from stream FPS and "
            "reconnect counts shown above.",
        ],
        "last_checked": utcnow_iso(),
        "server_time": utcnow().strftime("%d-%m-%Y %H:%M:%S UTC"),
    }


@router.post("/refresh-cameras")
async def refresh_cameras(_: dict = Depends(get_current_user)) -> dict:
    report = await pipeline.sync_cameras()
    return {"synced": True, "report": report, "at": utcnow_iso()}
