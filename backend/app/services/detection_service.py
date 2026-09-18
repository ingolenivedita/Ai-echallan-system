"""Modular violation detection.

Input : a camera frame (plus the source's ground truth for synthetic cameras)
Output: a list of detections, each with violation type, confidence, camera id,
        timestamp and an evidence image path.

Three interchangeable detectors are registered, chosen per call:

``GROQ_VISION``      - real AI. The frame is sent to a Groq vision model, which
                       reports which of the four violations it can see. Used
                       whenever ``GROQ_API_KEY`` is configured.
``OPENCV_HEURISTIC`` - offline computer-vision fallback for real footage. Uses
                       HOG person detection, dense optical flow for direction and
                       HSV colour analysis. Coarse by design; confidences are
                       deliberately capped.
``DEMO_SIMULATOR``   - only for synthetic demo cameras. Reads the scripted ground
                       truth of the rendered scene. Records produced this way are
                       stamped as simulated so they are never mistaken for AI
                       output.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import uuid
from typing import Any

import cv2
import numpy as np

from ..config import EVIDENCE_DIR, settings
from ..constants import (
    DEMO_SOURCE_SYNTHETIC,
    DETECTOR_GROQ,
    DETECTOR_HEURISTIC,
    MODE_DEMO,
    NO_HELMET,
    PROHIBITED_CONTAINER,
    TRIPLE_RIDING,
    VIOLATION_LABELS,
    WRONG_SIDE_DRIVING,
)
from ..utils import utcnow, utcnow_iso
from . import ai_service
from .camera_manager import encode_jpeg

logger = logging.getLogger("rto.detection")

DETECTOR_SIMULATOR = "DEMO_SIMULATOR"

_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# previous grayscale frame per camera, for optical-flow direction estimation
_previous_gray: dict[str, np.ndarray] = {}

_DIRECTION_VECTORS = {
    "LEFT_TO_RIGHT": (1.0, 0.0),
    "RIGHT_TO_LEFT": (-1.0, 0.0),
    "TOP_TO_BOTTOM": (0.0, 1.0),
    "BOTTOM_TO_TOP": (0.0, -1.0),
}


# --------------------------------------------------------------------------- #
# evidence
# --------------------------------------------------------------------------- #
def annotate(frame: np.ndarray, detections: list[dict], camera: dict) -> np.ndarray:
    """Draw violation boxes and labels for the stored evidence image."""
    canvas = frame.copy()
    height, width = canvas.shape[:2]

    for index, detection in enumerate(detections):
        box = detection.get("box")
        colour = (40, 60, 230)
        if box and len(box) == 4:
            x, y, box_width, box_height = (int(value) for value in box)
            x, y = max(x, 0), max(y, 0)
            cv2.rectangle(canvas, (x, y), (x + box_width, y + box_height), colour, 2)
            label = VIOLATION_LABELS.get(detection["violation_type"], detection["violation_type"])
            cv2.rectangle(canvas, (x, max(y - 22, 0)), (x + 210, max(y, 22)), colour, -1)
            cv2.putText(
                canvas,
                f"{label} {int(detection['confidence'] * 100)}%",
                (x + 4, max(y - 6, 14)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
        else:
            cv2.putText(
                canvas,
                f"{VIOLATION_LABELS.get(detection['violation_type'], '')} "
                f"{int(detection['confidence'] * 100)}%",
                (12, 60 + index * 26),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                colour,
                2,
            )

    banner = (
        f"EVIDENCE | {camera.get('camera_id', '')} | {camera.get('location', '')} | "
        f"{utcnow().strftime('%d-%m-%Y %H:%M:%S')} UTC"
    )
    cv2.rectangle(canvas, (0, height - 30), (width, height), (15, 15, 20), -1)
    cv2.putText(
        canvas, banner[:92], (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 240), 1
    )
    return canvas


def save_evidence(frame: np.ndarray, detections: list[dict], camera: dict) -> str:
    """Persist the annotated evidence image; returns its file name."""
    annotated = annotate(frame, detections, camera)
    encoded = encode_jpeg(annotated)
    if not encoded:
        return ""
    filename = (
        f"{camera.get('camera_id', 'CAM')}_"
        f"{utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
    )
    (EVIDENCE_DIR / filename).write_bytes(encoded)
    return filename


# --------------------------------------------------------------------------- #
# detector 1: simulated (synthetic demo cameras only)
# --------------------------------------------------------------------------- #
def detect_from_ground_truth(ground_truth: dict, camera: dict) -> dict:
    detections: list[dict] = []
    vehicles = ground_truth.get("vehicles") or []

    for vehicle in vehicles:
        box = vehicle.get("box")
        plate = vehicle.get("plate", "")
        base = {
            "box": box,
            "plate_text": plate,
            "vehicle_type": vehicle.get("vehicle_type", ""),
        }
        if vehicle.get("no_helmet"):
            riders = max(int(vehicle.get("riders") or 1), 1)
            without = riders - int(vehicle.get("helmets_worn") or 0)
            detections.append(
                {
                    **base,
                    "violation_type": NO_HELMET,
                    "confidence": round(random.uniform(0.86, 0.97), 3),
                    "reason": f"{without} of {riders} rider(s) without a helmet",
                }
            )
        if vehicle.get("triple_riding"):
            detections.append(
                {
                    **base,
                    "violation_type": TRIPLE_RIDING,
                    "confidence": round(random.uniform(0.88, 0.98), 3),
                    "reason": f"{vehicle.get('riders')} persons on a two-wheeler",
                }
            )
        if vehicle.get("wrong_side"):
            detections.append(
                {
                    **base,
                    "violation_type": WRONG_SIDE_DRIVING,
                    "confidence": round(random.uniform(0.82, 0.95), 3),
                    "reason": "Vehicle travelling against the lane direction",
                }
            )
        if vehicle.get("carries_container"):
            detections.append(
                {
                    **base,
                    "violation_type": PROHIBITED_CONTAINER,
                    "confidence": round(random.uniform(0.78, 0.93), 3),
                    "reason": "Cylinder / inflammable container carried on a two-wheeler",
                }
            )

    return {
        "detector": DETECTOR_SIMULATOR,
        "simulated": True,
        "detections": detections,
        "scene": (
            f"Synthetic demo scene with {ground_truth.get('vehicle_count', 0)} vehicle(s) "
            f"on {camera.get('camera_id', '')}"
        ),
        "vehicle_count": ground_truth.get("vehicle_count", 0),
        "notes": "Scripted demo scenario - not a real AI inference.",
    }


# --------------------------------------------------------------------------- #
# detector 2: OpenCV heuristics (real footage, no API key needed)
# --------------------------------------------------------------------------- #
def _detect_people(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    scale = 640 / max(frame.shape[1], 1)
    resized = cv2.resize(frame, None, fx=min(scale, 1.0), fy=min(scale, 1.0))
    try:
        boxes, weights = _hog.detectMultiScale(
            resized, winStride=(8, 8), padding=(8, 8), scale=1.05
        )
    except cv2.error:
        return []

    ratio = 1.0 / min(scale, 1.0)
    scores = (
        [float(value) for value in np.array(weights).flatten()]
        if weights is not None and len(weights)
        else [1.0] * len(boxes)
    )
    people: list[tuple[int, int, int, int]] = []
    for (x, y, width, height), weight in zip(boxes, scores):
        if weight < 0.35:
            continue
        people.append(
            (int(x * ratio), int(y * ratio), int(width * ratio), int(height * ratio))
        )
    return people


def _cluster(boxes: list[tuple[int, int, int, int]], gap: int = 90) -> list[list[tuple]]:
    clusters: list[list[tuple]] = []
    for box in sorted(boxes, key=lambda item: item[0]):
        placed = False
        for cluster in clusters:
            last = cluster[-1]
            if abs(box[0] - last[0]) < gap and abs(box[1] - last[1]) < gap:
                cluster.append(box)
                placed = True
                break
        if not placed:
            clusters.append([box])
    return clusters


def _helmet_absent(frame: np.ndarray, box: tuple[int, int, int, int]) -> tuple[bool, float]:
    """Very coarse helmet check on the head region of a person box."""
    x, y, width, height = box
    head = frame[
        max(y, 0) : max(y, 0) + max(int(height * 0.28), 8),
        max(x, 0) : max(x, 0) + max(width, 8),
    ]
    if head.size == 0:
        return False, 0.0

    hsv = cv2.cvtColor(head, cv2.COLOR_BGR2HSV)
    saturation = float(hsv[:, :, 1].mean())
    value = float(hsv[:, :, 2].mean())
    edges = cv2.Canny(cv2.cvtColor(head, cv2.COLOR_BGR2GRAY), 60, 160)
    edge_density = float(edges.mean())

    # A helmet is a smooth, fairly saturated or bright dome: low edge density.
    helmet_score = (saturation / 255) * 0.5 + (value / 255) * 0.3 + max(0.0, 1 - edge_density / 40) * 0.2
    absent = helmet_score < 0.42
    confidence = min(0.78, 0.5 + abs(0.42 - helmet_score))
    return absent, round(confidence, 3)


def _dominant_direction(camera_id: str, frame: np.ndarray) -> tuple[float, float, float]:
    """Return ``(dx, dy, magnitude)`` of the dominant motion via optical flow."""
    gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
    previous = _previous_gray.get(camera_id)
    _previous_gray[camera_id] = gray
    if previous is None or previous.shape != gray.shape:
        return 0.0, 0.0, 0.0

    flow = cv2.calcOpticalFlowFarneback(previous, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    moving = magnitude > 1.0
    if not moving.any():
        return 0.0, 0.0, 0.0

    dx = float(flow[..., 0][moving].mean())
    dy = float(flow[..., 1][moving].mean())
    return dx, dy, float(math.hypot(dx, dy))


def _detect_container(frame: np.ndarray) -> list[dict]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 130, 90), (12, 255, 255)) | cv2.inRange(
        hsv, (168, 130, 90), (180, 255, 255)
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    findings: list[dict] = []
    frame_area = frame.shape[0] * frame.shape[1]
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < frame_area * 0.0012 or area > frame_area * 0.08:
            continue
        x, y, width, height = cv2.boundingRect(contour)
        if height == 0:
            continue
        aspect = width / height
        fill = area / max(width * height, 1)
        if 0.35 <= aspect <= 1.5 and fill > 0.55:
            findings.append(
                {
                    "violation_type": PROHIBITED_CONTAINER,
                    "confidence": round(min(0.72, 0.45 + fill * 0.3), 3),
                    "box": [x, y, width, height],
                    "reason": "Compact high-saturation cylindrical object detected",
                }
            )
    return findings[:2]


def detect_with_opencv(frame: np.ndarray, camera: dict) -> dict:
    camera_id = str(camera.get("camera_id", ""))
    detections: list[dict] = []

    people = _detect_people(frame)
    clusters = _cluster(people)

    for cluster in clusters:
        if len(cluster) >= 3:
            xs = [box[0] for box in cluster]
            ys = [box[1] for box in cluster]
            widths = [box[0] + box[2] for box in cluster]
            heights = [box[1] + box[3] for box in cluster]
            detections.append(
                {
                    "violation_type": TRIPLE_RIDING,
                    "confidence": round(min(0.8, 0.55 + 0.07 * len(cluster)), 3),
                    "box": [min(xs), min(ys), max(widths) - min(xs), max(heights) - min(ys)],
                    "reason": f"{len(cluster)} persons detected on one vehicle footprint",
                }
            )

    for box in people[:4]:
        absent, confidence = _helmet_absent(frame, box)
        if absent:
            detections.append(
                {
                    "violation_type": NO_HELMET,
                    "confidence": confidence,
                    "box": list(box),
                    "reason": "No smooth helmet signature found in the head region",
                }
            )

    allowed = (camera.get("allowed_direction") or "ANY").upper()
    dx, dy, magnitude = _dominant_direction(camera_id, frame)
    if allowed in _DIRECTION_VECTORS and magnitude > 1.2:
        expected_x, expected_y = _DIRECTION_VECTORS[allowed]
        alignment = (dx * expected_x + dy * expected_y) / (magnitude or 1)
        if alignment < -0.45:
            detections.append(
                {
                    "violation_type": WRONG_SIDE_DRIVING,
                    "confidence": round(min(0.82, 0.5 + abs(alignment) * 0.35), 3),
                    "box": None,
                    "reason": (
                        f"Dominant motion opposes the permitted direction "
                        f"({allowed.replace('_', ' ').lower()})"
                    ),
                }
            )

    detections.extend(_detect_container(frame))

    return {
        "detector": DETECTOR_HEURISTIC,
        "simulated": False,
        "detections": detections,
        "scene": f"{len(people)} person(s), motion magnitude {magnitude:.2f}",
        "vehicle_count": len(clusters),
        "notes": (
            "OpenCV heuristic detector (HOG + optical flow + HSV). Coarse accuracy - "
            "configure GROQ_API_KEY for AI based detection."
        ),
    }


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def choose_detector(camera: dict, ground_truth: dict, preference: str = "auto") -> str:
    preference = (preference or "auto").lower()
    if preference in {"groq", DETECTOR_GROQ.lower()}:
        return DETECTOR_GROQ
    if preference in {"opencv", "heuristic", DETECTOR_HEURISTIC.lower()}:
        return DETECTOR_HEURISTIC
    if preference in {"simulator", DETECTOR_SIMULATOR.lower()}:
        return DETECTOR_SIMULATOR

    if ai_service.is_configured():
        return DETECTOR_GROQ
    is_synthetic = (
        (camera.get("mode") or MODE_DEMO).upper() == MODE_DEMO
        and (camera.get("demo_source_type") or "").upper() == DEMO_SOURCE_SYNTHETIC
        and (ground_truth or {}).get("source") == "SYNTHETIC"
    )
    return DETECTOR_SIMULATOR if is_synthetic else DETECTOR_HEURISTIC


async def analyse(
    camera: dict,
    frame: np.ndarray,
    ground_truth: dict | None = None,
    preference: str = "auto",
) -> dict:
    """Run the selected detector and return a normalised outcome."""
    ground_truth = ground_truth or {}
    detector = choose_detector(camera, ground_truth, preference)
    outcome: dict[str, Any]

    if detector == DETECTOR_GROQ:
        encoded = encode_jpeg(frame) or b""
        context = (
            f"Camera {camera.get('camera_id')} at {camera.get('location') or 'unknown location'}; "
            f"mode {camera.get('mode')}"
        )
        api_result = await ai_service.analyse_frame(encoded, context)
        if api_result["ok"]:
            outcome = {
                "detector": DETECTOR_GROQ,
                "simulated": False,
                "detections": api_result["data"].get("detections", []),
                "scene": api_result["data"].get("scene", ""),
                "vehicle_count": api_result["data"].get("vehicle_count"),
                "notes": f"Groq vision model {api_result['data'].get('model')}",
            }
        else:
            # Never invent an AI result - fall back and say so.
            fallback = await asyncio.to_thread(detect_with_opencv, frame, camera)
            fallback["notes"] = f"Groq unavailable ({api_result['message']}). {fallback['notes']}"
            outcome = fallback
    elif detector == DETECTOR_SIMULATOR:
        outcome = detect_from_ground_truth(ground_truth, camera)
    else:
        outcome = await asyncio.to_thread(detect_with_opencv, frame, camera)

    # normalise + threshold
    minimum = float(settings.detection_min_confidence)
    cleaned: list[dict] = []
    for detection in outcome.get("detections", []):
        confidence = float(detection.get("confidence") or 0)
        if confidence < minimum:
            continue
        cleaned.append(
            {
                "violation_type": detection["violation_type"],
                "confidence": round(confidence, 3),
                "box": detection.get("box"),
                "reason": detection.get("reason", ""),
                "plate_text": (detection.get("plate_text") or "").upper(),
                "vehicle_type": detection.get("vehicle_type", ""),
            }
        )

    outcome["detections"] = cleaned
    outcome["camera_id"] = camera.get("camera_id")
    outcome["analysed_at"] = utcnow_iso()
    outcome["min_confidence"] = minimum
    return outcome


def reset_camera_state(camera_id: str) -> None:
    _previous_gray.pop(str(camera_id), None)
