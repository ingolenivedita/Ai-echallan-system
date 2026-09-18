"""Domain constants: roles, violation catalogue, statuses, camera modes."""

from __future__ import annotations

# ----------------------------- roles ------------------------------------- #
ROLE_ADMIN = "admin"
ROLE_OFFICER = "officer"
ROLES = [ROLE_ADMIN, ROLE_OFFICER]

ROLE_LABELS = {
    ROLE_ADMIN: "Administrator",
    ROLE_OFFICER: "Traffic Officer",
}

# --------------------------- violations ---------------------------------- #
NO_HELMET = "NO_HELMET"
TRIPLE_RIDING = "TRIPLE_RIDING"
WRONG_SIDE_DRIVING = "WRONG_SIDE_DRIVING"
PROHIBITED_CONTAINER = "PROHIBITED_CONTAINER"

VIOLATION_CATALOGUE: list[dict] = [
    {
        "code": NO_HELMET,
        "label": "No Helmet",
        "section": "MVA Sec. 129 / 194D",
        "default_fine": 1000,
        "severity": "high",
        "description": "Rider or pillion travelling without a protective helmet.",
    },
    {
        "code": TRIPLE_RIDING,
        "label": "Triple Riding",
        "section": "MVA Sec. 128 / 194C",
        "default_fine": 1000,
        "severity": "high",
        "description": "More than two persons riding on a two-wheeler.",
    },
    {
        "code": WRONG_SIDE_DRIVING,
        "label": "Wrong Side Driving",
        "section": "MVA Sec. 184",
        "default_fine": 2000,
        "severity": "critical",
        "description": "Vehicle moving against the permitted direction of the lane.",
    },
    {
        "code": PROHIBITED_CONTAINER,
        "label": "Explosive / Prohibited Container",
        "section": "MVA Sec. 190(2)",
        "default_fine": 5000,
        "severity": "critical",
        "description": (
            "Vehicle carrying a cylinder, drum or container of explosive / "
            "inflammable goods without authorisation."
        ),
    },
]

VIOLATION_TYPES = [item["code"] for item in VIOLATION_CATALOGUE]
VIOLATION_LABELS = {item["code"]: item["label"] for item in VIOLATION_CATALOGUE}
DEFAULT_FINES = {item["code"]: item["default_fine"] for item in VIOLATION_CATALOGUE}

# --------------------------- statuses ------------------------------------ #
VIOLATION_PENDING = "PENDING_REVIEW"
VIOLATION_APPROVED = "APPROVED"
VIOLATION_REJECTED = "REJECTED"
VIOLATION_CHALLANED = "CHALLAN_ISSUED"
VIOLATION_STATUSES = [
    VIOLATION_PENDING,
    VIOLATION_APPROVED,
    VIOLATION_REJECTED,
    VIOLATION_CHALLANED,
]

CHALLAN_PENDING = "PENDING"
CHALLAN_PAID = "PAID"
CHALLAN_CANCELLED = "CANCELLED"
CHALLAN_DISPUTED = "DISPUTED"
CHALLAN_STATUSES = [CHALLAN_PENDING, CHALLAN_PAID, CHALLAN_CANCELLED, CHALLAN_DISPUTED]

# --------------------------- cameras ------------------------------------- #
MODE_LIVE = "LIVE"
MODE_DEMO = "DEMO"
CAMERA_MODES = [MODE_LIVE, MODE_DEMO]

DEMO_SOURCE_SYNTHETIC = "SYNTHETIC"
DEMO_SOURCE_VIDEO = "VIDEO"
DEMO_SOURCE_IMAGE = "IMAGE"
DEMO_SOURCES = [DEMO_SOURCE_SYNTHETIC, DEMO_SOURCE_VIDEO, DEMO_SOURCE_IMAGE]

STATUS_ONLINE = "ONLINE"
STATUS_OFFLINE = "OFFLINE"
STATUS_CONNECTING = "CONNECTING"
STATUS_DISABLED = "DISABLED"

# --------------------------- detection ----------------------------------- #
DETECTOR_GROQ = "GROQ_VISION"
DETECTOR_HEURISTIC = "OPENCV_HEURISTIC"

# --------------------------- alerts -------------------------------------- #
ALERT_OPEN = "OPEN"
ALERT_ACKNOWLEDGED = "ACKNOWLEDGED"
ALERT_RESOLVED = "RESOLVED"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
