"""The asyncio processing pipeline.

Two background tasks run for the lifetime of the application:

``camera_sync_loop``  keeps the capture threads matching the database, mirrors
                     each camera's live health back into MongoDB, and raises or
                     resolves maintenance alerts when a camera drops or returns.
``detection_loop``    samples the latest frame of every online camera, runs the
                     detection service, stores violations with evidence images,
                     resolves the number plate through ANPR and (when enabled)
                     issues the challan and sends the SMS.

Each camera is processed in its own task with its own error handling, so a
failure on one camera cannot stall the others.
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..constants import (
    ALERT_OPEN,
    ALERT_RESOLVED,
    SEVERITY_WARNING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    VIOLATION_LABELS,
    VIOLATION_PENDING,
)
from ..database import ALERTS, CAMERAS, VIOLATIONS, coll
from ..utils import utcnow_iso
from . import anpr_service, detection_service
from .app_settings import get_settings_document
from .camera_manager import camera_manager, encode_jpeg
from .challan_service import issue_challan
from .rules_service import rules_map

logger = logging.getLogger("rto.pipeline")

CAMERA_SYNC_INTERVAL = 10.0
ALERT_TYPE_OFFLINE = "CAMERA_OFFLINE"

# (camera_id, violation_type) -> monotonic timestamp of the last stored violation
_cooldown: dict[tuple[str, str], float] = {}


def _cooldown_passed(camera_id: str, violation_type: str, cooldown: float) -> bool:
    """Stop the same offence on the same camera being recorded repeatedly."""
    key = (str(camera_id), violation_type)
    now = time.monotonic()
    last = _cooldown.get(key)
    if last is not None and now - last < cooldown:
        return False
    _cooldown[key] = now
    return True


class ProcessingPipeline:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self.last_detection_cycle: str | None = None
        self.last_sync_cycle: str | None = None
        self.cycles = 0
        self.violations_recorded = 0
        self.challans_issued = 0
        self.last_error: str = ""

    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.sync_cameras()
        self._tasks = [
            asyncio.create_task(self._camera_sync_loop(), name="camera-sync"),
            asyncio.create_task(self._detection_loop(), name="detection"),
        ]
        logger.info("Processing pipeline started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks = []
        camera_manager.stop_all()
        logger.info("Processing pipeline stopped")

    def status(self) -> dict:
        return {
            "running": self._running,
            "tasks": [task.get_name() for task in self._tasks if not task.done()],
            "cycles": self.cycles,
            "violations_recorded": self.violations_recorded,
            "challans_issued": self.challans_issued,
            "last_detection_cycle": self.last_detection_cycle,
            "last_sync_cycle": self.last_sync_cycle,
            "last_error": self.last_error,
        }

    # ------------------------------------------------------------------ #
    async def sync_cameras(self) -> dict:
        cameras = await coll(CAMERAS).find({}).to_list(200)
        report = camera_manager.sync(cameras)
        await self._mirror_health(cameras)
        self.last_sync_cycle = utcnow_iso()
        return report

    async def _camera_sync_loop(self) -> None:
        while self._running:
            try:
                await self.sync_cameras()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"camera sync: {exc}"
                logger.exception("Camera sync failed")
            await asyncio.sleep(CAMERA_SYNC_INTERVAL)

    async def _mirror_health(self, cameras: list[dict]) -> None:
        """Copy live thread state into MongoDB and manage offline alerts."""
        for camera in cameras:
            camera_id = str(camera.get("camera_id"))
            worker = camera_manager.get(camera_id)

            if not camera.get("enabled", True):
                await coll(CAMERAS).update_one(
                    {"_id": camera["_id"]},
                    {"$set": {"status": "DISABLED", "fps": 0, "updated_at": utcnow_iso()}},
                )
                continue

            if worker is None:
                continue

            health = worker.health()
            await coll(CAMERAS).update_one(
                {"_id": camera["_id"]},
                {
                    "$set": {
                        "status": health["status"],
                        "fps": health["fps"],
                        "resolution": health["resolution"],
                        "last_seen": health["last_seen"],
                        "last_frame_at": health["last_frame_at"],
                        "offline_since": health["offline_since"],
                        "connection_error": health["connection_error"],
                        "frames_captured": health["frames_captured"],
                        "reconnect_attempts": health["reconnect_attempts"],
                        "source_kind": health["source_kind"],
                        "updated_at": utcnow_iso(),
                    }
                },
            )

            if health["status"] == STATUS_OFFLINE:
                await self._raise_offline_alert(camera, health)
            elif health["status"] == STATUS_ONLINE:
                await self._resolve_offline_alert(camera)

    async def _raise_offline_alert(self, camera: dict, health: dict) -> None:
        camera_id = str(camera.get("camera_id"))
        open_alert = await coll(ALERTS).find_one(
            {"camera_id": camera_id, "type": ALERT_TYPE_OFFLINE, "status": ALERT_OPEN}
        )
        if open_alert:
            await coll(ALERTS).update_one(
                {"_id": open_alert["_id"]},
                {
                    "$set": {
                        "detail": health["connection_error"],
                        "last_checked_at": utcnow_iso(),
                        "reconnect_attempts": health["reconnect_attempts"],
                    }
                },
            )
            return

        await coll(ALERTS).insert_one(
            {
                "type": ALERT_TYPE_OFFLINE,
                "camera_id": camera_id,
                "camera_name": camera.get("name", ""),
                "location": camera.get("location", ""),
                "severity": SEVERITY_WARNING,
                "status": ALERT_OPEN,
                "message": (
                    f"{camera.get('name') or camera_id} is offline. "
                    "Please check camera/network connection."
                ),
                "detail": health["connection_error"],
                "created_at": utcnow_iso(),
                "last_checked_at": utcnow_iso(),
                "reconnect_attempts": health["reconnect_attempts"],
                "acknowledged_by": "",
                "resolved_at": None,
            }
        )
        logger.warning("Maintenance alert raised: %s offline", camera_id)

    async def _resolve_offline_alert(self, camera: dict) -> None:
        camera_id = str(camera.get("camera_id"))
        await coll(ALERTS).update_many(
            {
                "camera_id": camera_id,
                "type": ALERT_TYPE_OFFLINE,
                "status": {"$ne": ALERT_RESOLVED},
            },
            {
                "$set": {
                    "status": ALERT_RESOLVED,
                    "resolved_at": utcnow_iso(),
                    "resolution": "Camera reconnected and is streaming again.",
                }
            },
        )

    # ------------------------------------------------------------------ #
    async def _detection_loop(self) -> None:
        while self._running:
            interval = 8.0
            try:
                app_settings = await get_settings_document()
                interval = float(app_settings.get("detection_interval_seconds") or 8.0)
                await self.run_detection_cycle(app_settings)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"detection cycle: {exc}"
                logger.exception("Detection cycle failed")
            await asyncio.sleep(max(interval, 2.0))

    async def run_detection_cycle(self, app_settings: dict | None = None) -> dict:
        app_settings = app_settings or await get_settings_document()
        rules = await rules_map()
        cameras = await coll(CAMERAS).find(
            {"enabled": True, "detection_enabled": True}
        ).to_list(200)

        results = await asyncio.gather(
            *(self._process_camera(camera, rules, app_settings) for camera in cameras),
            return_exceptions=True,
        )

        stored = 0
        for camera, outcome in zip(cameras, results):
            if isinstance(outcome, Exception):
                logger.warning(
                    "Detection failed for %s: %s", camera.get("camera_id"), outcome
                )
                continue
            stored += outcome

        self.cycles += 1
        self.last_detection_cycle = utcnow_iso()
        return {
            "cameras_processed": len(cameras),
            "violations_recorded": stored,
            "at": self.last_detection_cycle,
        }

    async def process_camera_once(self, camera: dict) -> int:
        """Run a single detection pass on one camera (used by 'Detect now')."""
        return await self._process_camera(
            camera, await rules_map(), await get_settings_document()
        )

    async def _process_camera(
        self, camera: dict, rules: dict, app_settings: dict
    ) -> int:
        camera_id = str(camera.get("camera_id"))
        worker = camera_manager.get(camera_id)
        if worker is None or worker.status != STATUS_ONLINE:
            return 0

        frame, ground_truth = worker.snapshot_frame()
        if frame is None:
            return 0

        outcome = await detection_service.analyse(camera, frame, ground_truth)
        worker.detections_run += 1
        worker.last_detection_at = utcnow_iso()

        cooldown = float(app_settings.get("detection_cooldown_seconds") or 90.0)
        detections = [
            detection
            for detection in outcome.get("detections", [])
            if rules.get(detection["violation_type"], {}).get("enabled", True)
            and detection["confidence"]
            >= float(rules.get(detection["violation_type"], {}).get("min_confidence") or 0.5)
            and _cooldown_passed(camera_id, detection["violation_type"], cooldown)
        ]
        if not detections:
            return 0

        plate_number, plate_source, plate_confidence = await self._resolve_plate(
            frame, detections, camera_id, outcome
        )
        evidence_image = detection_service.save_evidence(frame, detections, camera)

        stored = 0
        for detection in detections:
            document = {
                "camera_id": camera_id,
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
                "plate_confidence": plate_confidence,
                "vehicle_type": detection.get("vehicle_type", ""),
                "evidence_image": evidence_image,
                "detected_at": utcnow_iso(),
                "status": VIOLATION_PENDING,
                "reviewed_by": "",
                "reviewed_at": None,
                "remarks": "",
                "challan_id": None,
                "challan_number": None,
                "created_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
            }
            inserted = await coll(VIOLATIONS).insert_one(document)
            document["_id"] = inserted.inserted_id
            stored += 1
            self.violations_recorded += 1
            worker.violation_count += 1

            rule = rules.get(detection["violation_type"], {})
            auto_enabled = bool(app_settings.get("auto_challan")) and bool(
                rule.get("auto_challan", True)
            )
            if auto_enabled and plate_number:
                try:
                    created = await issue_challan(document, actor="AI-AUTO")
                    if created["created"]:
                        self.challans_issued += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Auto challan failed: %s", exc)

        await coll(CAMERAS).update_one(
            {"_id": camera["_id"]},
            {
                "$inc": {"violation_count": stored},
                "$set": {
                    "last_detection_at": utcnow_iso(),
                    "last_detector": outcome.get("detector", ""),
                },
            },
        )
        return stored

    async def _resolve_plate(
        self, frame, detections: list[dict], camera_id: str, outcome: dict
    ) -> tuple[str, str, float | None]:
        """Prefer a plate the detector already read, else call the ANPR API."""
        for detection in detections:
            text = (detection.get("plate_text") or "").strip().upper()
            if len(text) >= 6:
                source = "SIMULATED" if outcome.get("simulated") else "AI_VISION"
                return text, source, detection.get("confidence")

        encoded = encode_jpeg(frame) or b""
        anpr = await anpr_service.read_plate(encoded, camera_id)
        data = anpr.get("data", {})
        return (
            (data.get("plate_number") or "").upper(),
            data.get("plate_source") or ("DEMO" if not anpr["configured"] else "ANPR"),
            data.get("confidence"),
        )


pipeline = ProcessingPipeline()
