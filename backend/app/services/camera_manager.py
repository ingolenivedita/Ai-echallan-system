"""Multi-camera capture engine.

Every camera runs in its **own daemon thread** with its own capture handle,
reconnect loop and health counters, so two or three (or ten) cameras stream at
the same time and one camera failing never stops the others - a hard requirement
of this project.

Supported sources per camera:
  * ``LIVE`` - RTSP / IP camera stream through OpenCV + FFmpeg
  * ``DEMO`` with ``SYNTHETIC`` - procedurally rendered traffic scene
  * ``DEMO`` with ``VIDEO``     - uploaded or sample traffic video (looped)
  * ``DEMO`` with ``IMAGE``     - uploaded still image

The threads never touch the database or any HTTP API: they only produce frames.
Persistence (violations, alerts) happens in the asyncio pipeline, which keeps the
capture loop fast and the data layer single-threaded.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import cv2
import numpy as np

from ..constants import (
    DEMO_SOURCE_IMAGE,
    DEMO_SOURCE_SYNTHETIC,
    DEMO_SOURCE_VIDEO,
    MODE_DEMO,
    MODE_LIVE,
    STATUS_CONNECTING,
    STATUS_DISABLED,
    STATUS_OFFLINE,
    STATUS_ONLINE,
)
from ..utils import utcnow_iso
from .synthetic import SyntheticTrafficSource

logger = logging.getLogger("rto.camera")

# Keep RTSP on TCP and give up on a dead stream instead of blocking forever.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000|max_delay;500000",
)

JPEG_QUALITY = 78
TARGET_FPS = 12.0
MAX_READ_FAILURES = 12
RECONNECT_BACKOFF = [2, 4, 6, 10, 15]

# How long a failing camera may keep reporting CONNECTING while it retries.
# After this it stays OFFLINE so health and maintenance alerts do not flap.
OFFLINE_GRACE_SECONDS = 20.0

_PLACEHOLDER_SIZE = (540, 960, 3)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def build_rtsp_url(config: dict) -> str:
    """Compose the stream URL, injecting credentials when they are stored apart."""
    url = (config.get("rtsp_url") or "").strip()
    username = (config.get("username") or "").strip()
    password = (config.get("password") or "").strip()
    ip_address = (config.get("ip_address") or "").strip()

    if not url and ip_address:
        url = f"rtsp://{ip_address}:554/stream"

    if not url:
        return ""

    if username and "@" not in url.split("//", 1)[-1].split("/")[0]:
        parsed = urlparse(url)
        credentials = quote(username, safe="")
        if password:
            credentials += f":{quote(password, safe='')}"
        netloc = f"{credentials}@{parsed.netloc}"
        url = urlunparse(parsed._replace(netloc=netloc))
    return url


def redact_url(url: str) -> str:
    """Hide credentials before a URL is shown in the UI or a log line."""
    if not url or "@" not in url:
        return url
    scheme, _, rest = url.partition("//")
    credentials, _, host = rest.partition("@")
    user = credentials.split(":")[0]
    return f"{scheme}//{user}:****@{host}"


def resolve_source(config: dict) -> tuple[str, str]:
    """Return ``(kind, target)`` where kind is live|video|image|synthetic."""
    if (config.get("mode") or MODE_DEMO).upper() == MODE_LIVE:
        return "live", build_rtsp_url(config)

    demo_type = (config.get("demo_source_type") or DEMO_SOURCE_SYNTHETIC).upper()
    path = (config.get("demo_source_path") or "").strip()
    if demo_type == DEMO_SOURCE_VIDEO and path:
        return "video", path
    if demo_type == DEMO_SOURCE_IMAGE and path:
        return "image", path
    return "synthetic", ""


def draw_overlay(frame: np.ndarray, worker: "CameraWorker") -> np.ndarray:
    """Burn camera name, mode badge and timestamp into the frame."""
    canvas = frame
    height, width = canvas.shape[:2]
    cv2.rectangle(canvas, (0, 0), (width, 34), (18, 20, 28), -1)
    cv2.rectangle(canvas, (0, height - 26), (width, height), (18, 20, 28), -1)

    name = f"{worker.config.get('camera_id', '')} | {worker.config.get('name', '')}"
    cv2.putText(
        canvas, name[:52], (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1
    )

    demo = (worker.config.get("mode") or MODE_DEMO).upper() == MODE_DEMO
    badge = "DEMO MODE" if demo else "LIVE"
    badge_colour = (0, 170, 255) if demo else (60, 200, 90)
    badge_width = 108 if demo else 62
    cv2.rectangle(canvas, (width - badge_width - 10, 7), (width - 10, 28), badge_colour, -1)
    cv2.putText(
        canvas,
        badge,
        (width - badge_width - 2, 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (20, 20, 20),
        2,
    )

    footer = (
        f"{worker.config.get('location', '') or 'Location not set'}   "
        f"{time.strftime('%d-%m-%Y %H:%M:%S')}   {worker.fps:.1f} FPS"
    )
    cv2.putText(
        canvas, footer[:78], (10, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 205, 215), 1
    )
    return canvas


def placeholder_frame(title: str, subtitle: str, colour=(30, 34, 46)) -> np.ndarray:
    frame = np.full(_PLACEHOLDER_SIZE, colour, dtype=np.uint8)
    cv2.putText(
        frame, title[:34], (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (235, 235, 240), 2
    )
    cv2.putText(
        frame, subtitle[:70], (60, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 160, 180), 1
    )
    return frame


def encode_jpeg(frame: np.ndarray) -> bytes | None:
    success, buffer = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    )
    return buffer.tobytes() if success else None


# --------------------------------------------------------------------------- #
# worker
# --------------------------------------------------------------------------- #
class CameraWorker(threading.Thread):
    """Captures frames from a single camera, forever, independently."""

    FINGERPRINT_FIELDS = (
        "mode",
        "rtsp_url",
        "ip_address",
        "username",
        "password",
        "demo_source_type",
        "demo_source_path",
        "enabled",
    )

    def __init__(self, config: dict):
        super().__init__(daemon=True, name=f"camera-{config.get('camera_id')}")
        self.config = dict(config)
        self.camera_id: str = str(config.get("camera_id"))
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._frame: np.ndarray | None = None
        self._ground_truth: dict = {}

        self.status = STATUS_CONNECTING
        self.last_error = ""
        self.last_frame_at: str | None = None
        self.last_seen: str | None = None
        self.offline_since: str | None = None
        self._offline_monotonic: float | None = None
        self.started_at = utcnow_iso()
        self.fps = 0.0
        self.frame_count = 0
        self.last_frame_monotonic: float | None = None
        self.reconnect_attempts = 0
        self.violation_count = 0
        self.detections_run = 0
        self.last_detection_at: str | None = None
        self.resolution = ""
        self.source_kind, target = resolve_source(self.config)
        self.source_label = redact_url(target) if self.source_kind == "live" else target

    # ------------------------------------------------------------------ #
    def fingerprint(self) -> tuple:
        return tuple(str(self.config.get(field, "")) for field in self.FINGERPRINT_FIELDS)

    def update_config(self, config: dict) -> None:
        """Apply changes that do not need the capture session to restart."""
        with self._lock:
            self.config.update(config)

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------ #
    def run(self) -> None:  # pragma: no cover - long running loop
        attempt = 0
        while not self._stop_event.is_set():
            try:
                self._publish_status_frame(STATUS_CONNECTING, "Connecting to source...")
                self._run_session()
                attempt = 0
            except Exception as exc:  # noqa: BLE001 - a camera must never crash the app
                self._mark_offline(f"{type(exc).__name__}: {exc}")
                logger.warning("[%s] capture error: %s", self.camera_id, exc)

            if self._stop_event.is_set():
                break

            delay = RECONNECT_BACKOFF[min(attempt, len(RECONNECT_BACKOFF) - 1)]
            attempt += 1
            self.reconnect_attempts += 1
            self._stop_event.wait(delay)

        self.status = STATUS_DISABLED
        logger.info("[%s] capture thread stopped", self.camera_id)

    # ------------------------------------------------------------------ #
    def _run_session(self) -> None:
        kind, target = resolve_source(self.config)
        self.source_kind = kind
        self.source_label = redact_url(target) if kind == "live" else target

        if kind == "synthetic":
            self._loop_synthetic()
        elif kind == "image":
            self._loop_image(target)
        elif kind == "video":
            self._loop_video(target)
        else:
            self._loop_live(target)

    # -------------------------- source loops -------------------------- #
    def _loop_synthetic(self) -> None:
        source = SyntheticTrafficSource(camera_label=self.camera_id)
        interval = 1.0 / TARGET_FPS
        while not self._stop_event.is_set():
            frame, ground_truth = source.read()
            self._publish(frame, ground_truth)
            self._stop_event.wait(interval)

    def _loop_image(self, path: str) -> None:
        image = cv2.imread(path)
        if image is None:
            raise RuntimeError(f"Uploaded image could not be read: {Path(path).name}")
        while not self._stop_event.is_set():
            self._publish(image.copy(), {"source": "IMAGE", "path": path})
            self._stop_event.wait(1.0)

    def _loop_video(self, path: str) -> None:
        if not Path(path).exists():
            raise RuntimeError(f"Demo video not found: {path}")
        capture = cv2.VideoCapture(path)
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open the video file: {Path(path).name}")

        native_fps = capture.get(cv2.CAP_PROP_FPS) or TARGET_FPS
        interval = 1.0 / max(min(native_fps, 25.0), 5.0)
        try:
            failures = 0
            while not self._stop_event.is_set():
                success, frame = capture.read()
                if not success or frame is None:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop the clip
                    failures += 1
                    if failures > 3:
                        raise RuntimeError("Video file ended and could not be rewound")
                    continue
                failures = 0
                self._publish(frame, {"source": "VIDEO", "path": path})
                self._stop_event.wait(interval)
        finally:
            capture.release()

    def _loop_live(self, url: str) -> None:
        if not url:
            raise RuntimeError(
                "No RTSP URL or IP address configured for this camera in LIVE mode"
            )
        capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        except cv2.error:
            pass
        if not capture.isOpened():
            raise RuntimeError(f"Unable to connect to {redact_url(url)}")

        try:
            failures = 0
            while not self._stop_event.is_set():
                success, frame = capture.read()
                if not success or frame is None:
                    failures += 1
                    if failures >= MAX_READ_FAILURES:
                        raise RuntimeError("Stream stopped delivering frames")
                    self._stop_event.wait(0.25)
                    continue
                failures = 0
                self._publish(frame, {"source": "RTSP"})
        finally:
            capture.release()

    # ---------------------------- publishing -------------------------- #
    def _publish(self, frame: np.ndarray, ground_truth: dict) -> None:
        now = time.time()
        if self.frame_count and self.last_frame_monotonic:
            delta = now - self.last_frame_monotonic
            if delta > 0:
                instant = 1.0 / delta
                self.fps = round(instant if not self.fps else self.fps * 0.8 + instant * 0.2, 2)
        self.last_frame_monotonic = now
        self.frame_count += 1
        self.resolution = f"{frame.shape[1]}x{frame.shape[0]}"

        annotated = draw_overlay(frame.copy(), self)
        encoded = encode_jpeg(annotated)

        with self._lock:
            self._frame = frame
            self._ground_truth = ground_truth
            if encoded:
                self._jpeg = encoded

        self.status = STATUS_ONLINE
        self.last_error = ""
        self.offline_since = None
        self._offline_monotonic = None
        self.last_frame_at = utcnow_iso()
        self.last_seen = self.last_frame_at

    def _mark_offline(self, error: str) -> None:
        self.status = STATUS_OFFLINE
        self.last_error = error[:300]
        self.fps = 0.0
        if not self.offline_since:
            self.offline_since = utcnow_iso()
            self._offline_monotonic = time.monotonic()
        self._publish_status_frame(STATUS_OFFLINE, error)

    def _publish_status_frame(self, status: str, message: str) -> None:
        if status == STATUS_OFFLINE:
            frame = placeholder_frame(
                f"{self.camera_id} OFFLINE", message, colour=(28, 24, 46)
            )
        else:
            frame = placeholder_frame(f"{self.camera_id} CONNECTING", message)
        encoded = encode_jpeg(draw_overlay(frame, self))
        with self._lock:
            if encoded:
                self._jpeg = encoded
        if status == STATUS_CONNECTING and self.status != STATUS_ONLINE:
            failing_for = (
                time.monotonic() - self._offline_monotonic
                if self._offline_monotonic is not None
                else 0.0
            )
            if self.offline_since and failing_for >= OFFLINE_GRACE_SECONDS:
                self.status = STATUS_OFFLINE
            else:
                self.status = STATUS_CONNECTING

    # ------------------------------ reads ----------------------------- #
    def snapshot_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def snapshot_frame(self) -> tuple[np.ndarray | None, dict]:
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            return frame, dict(self._ground_truth)

    def health(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "name": self.config.get("name"),
            "location": self.config.get("location"),
            "ip_address": self.config.get("ip_address"),
            "mode": (self.config.get("mode") or MODE_DEMO).upper(),
            "demo_source_type": self.config.get("demo_source_type"),
            "status": self.status,
            "online": self.status == STATUS_ONLINE,
            "fps": self.fps,
            "resolution": self.resolution,
            "frames_captured": self.frame_count,
            "last_frame_at": self.last_frame_at,
            "last_seen": self.last_seen,
            "offline_since": self.offline_since,
            "connection_error": self.last_error,
            "reconnect_attempts": self.reconnect_attempts,
            "violation_count": self.violation_count,
            "detections_run": self.detections_run,
            "last_detection_at": self.last_detection_at,
            "source_kind": self.source_kind,
            "source": self.source_label,
            "detection_enabled": bool(self.config.get("detection_enabled", True)),
            "thread_alive": self.is_alive(),
            "started_at": self.started_at,
        }


# --------------------------------------------------------------------------- #
# manager
# --------------------------------------------------------------------------- #
class CameraManager:
    """Owns one :class:`CameraWorker` per enabled camera."""

    def __init__(self) -> None:
        self.workers: dict[str, CameraWorker] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def sync(self, cameras: list[dict]) -> dict:
        """Start, stop and restart workers so they match the database."""
        report = {"started": [], "stopped": [], "restarted": [], "running": []}
        wanted = {
            str(camera.get("camera_id")): camera
            for camera in cameras
            if camera.get("enabled", True)
        }

        with self._lock:
            for camera_id in list(self.workers):
                if camera_id not in wanted:
                    self.workers.pop(camera_id).stop()
                    report["stopped"].append(camera_id)

            for camera_id, camera in wanted.items():
                worker = self.workers.get(camera_id)
                if worker is None or not worker.is_alive():
                    self._start(camera)
                    report["started"].append(camera_id)
                    continue

                candidate = CameraWorker.FINGERPRINT_FIELDS
                changed = any(
                    str(worker.config.get(field, "")) != str(camera.get(field, ""))
                    for field in candidate
                )
                if changed:
                    worker.stop()
                    self._start(camera)
                    report["restarted"].append(camera_id)
                else:
                    worker.update_config(camera)
                    report["running"].append(camera_id)
        return report

    def _start(self, camera: dict) -> CameraWorker:
        worker = CameraWorker(camera)
        self.workers[str(camera.get("camera_id"))] = worker
        worker.start()
        logger.info(
            "[%s] capture thread started (%s)", worker.camera_id, worker.source_kind
        )
        return worker

    def restart(self, camera: dict) -> None:
        with self._lock:
            existing = self.workers.pop(str(camera.get("camera_id")), None)
            if existing:
                existing.stop()
            if camera.get("enabled", True):
                self._start(camera)

    def stop_camera(self, camera_id: str) -> None:
        with self._lock:
            worker = self.workers.pop(str(camera_id), None)
        if worker:
            worker.stop()

    def stop_all(self) -> None:
        with self._lock:
            workers = list(self.workers.values())
            self.workers.clear()
        for worker in workers:
            worker.stop()

    # ------------------------------------------------------------------ #
    def get(self, camera_id: str) -> CameraWorker | None:
        return self.workers.get(str(camera_id))

    def health_all(self) -> list[dict]:
        return [worker.health() for worker in list(self.workers.values())]

    def summary(self) -> dict:
        health = self.health_all()
        online = sum(1 for item in health if item["online"])
        return {
            "total_running": len(health),
            "online": online,
            "offline": len(health) - online,
            "average_fps": round(
                sum(item["fps"] for item in health) / len(health), 2
            )
            if health
            else 0.0,
        }


camera_manager = CameraManager()


# --------------------------------------------------------------------------- #
# connection test (blocking - callers run it in a threadpool)
# --------------------------------------------------------------------------- #
def test_camera_connection(config: dict, timeout: float = 12.0) -> dict:
    """Try to open a camera source and grab one frame."""
    kind, target = resolve_source(config)
    started = time.perf_counter()

    if kind == "synthetic":
        frame, _ = SyntheticTrafficSource().read()
        return {
            "ok": True,
            "mode": "DEMO",
            "source_kind": kind,
            "message": "Synthetic demo source is always available.",
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "source": "Built-in synthetic traffic generator",
        }

    if kind == "image":
        image = cv2.imread(target)
        ok = image is not None
        return {
            "ok": ok,
            "mode": "DEMO",
            "source_kind": kind,
            "message": "Image loaded." if ok else "Image file could not be read.",
            "resolution": f"{image.shape[1]}x{image.shape[0]}" if ok else "",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "source": Path(target).name,
        }

    if not target:
        return {
            "ok": False,
            "mode": "LIVE" if kind == "live" else "DEMO",
            "source_kind": kind,
            "message": "No RTSP URL / file configured for this camera.",
            "resolution": "",
            "latency_ms": 0,
            "source": "",
        }

    capture = (
        cv2.VideoCapture(target, cv2.CAP_FFMPEG)
        if kind == "live"
        else cv2.VideoCapture(target)
    )
    try:
        if not capture.isOpened():
            return {
                "ok": False,
                "mode": "LIVE" if kind == "live" else "DEMO",
                "source_kind": kind,
                "message": (
                    f"Could not connect to {redact_url(target)}. Check the IP address, "
                    "port, credentials and that the camera is on the same network."
                ),
                "resolution": "",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "source": redact_url(target),
            }

        frame = None
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            success, candidate = capture.read()
            if success and candidate is not None:
                frame = candidate
                break

        latency = int((time.perf_counter() - started) * 1000)
        if frame is None:
            return {
                "ok": False,
                "mode": "LIVE" if kind == "live" else "DEMO",
                "source_kind": kind,
                "message": "Connected, but no frame was received before the timeout.",
                "resolution": "",
                "latency_ms": latency,
                "source": redact_url(target),
            }

        return {
            "ok": True,
            "mode": "LIVE" if kind == "live" else "DEMO",
            "source_kind": kind,
            "message": "Connected and received a frame.",
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
            "latency_ms": latency,
            "source": redact_url(target),
        }
    finally:
        capture.release()
