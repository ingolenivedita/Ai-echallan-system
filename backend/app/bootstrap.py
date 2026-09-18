"""First-run bootstrap: demo users, three demo cameras, rules and sample vehicles.

This runs automatically at startup but only creates what is missing, so it is
safe on every restart. ``backend/seed.py`` calls the same helpers and can also
generate sample violations/challans for a demo run.
"""

from __future__ import annotations

import logging

from .constants import (
    DEMO_SOURCE_SYNTHETIC,
    MODE_DEMO,
    ROLE_ADMIN,
    ROLE_OFFICER,
    STATUS_CONNECTING,
)
from .database import CAMERAS, USERS, VEHICLES, coll
from .security import hash_password
from .services.rules_service import ensure_rules
from .utils import utcnow_iso

logger = logging.getLogger("rto.bootstrap")

DEMO_USERS = [
    {
        "user_id": "ADMIN001",
        "password": "Admin@123",
        "name": "R. Krishnan",
        "role": ROLE_ADMIN,
        "designation": "RTO Administrator",
        "phone": "9000000001",
        "email": "admin@rto.gov.in",
        "station": "RTO Head Office",
    },
    {
        "user_id": "OFFICER001",
        "password": "Officer@123",
        "name": "S. Meena",
        "role": ROLE_OFFICER,
        "designation": "Traffic Sub-Inspector",
        "phone": "9000000002",
        "email": "officer1@rto.gov.in",
        "station": "City Traffic Police Station",
    },
    {
        "user_id": "OFFICER002",
        "password": "Officer@123",
        "name": "A. Devaraj",
        "role": ROLE_OFFICER,
        "designation": "Traffic Constable",
        "phone": "9000000003",
        "email": "officer2@rto.gov.in",
        "station": "Highway Patrol Unit",
    },
]

DEMO_CAMERAS = [
    {
        "camera_id": "CAM-01",
        "name": "Camera 1",
        "ip_address": "192.168.1.101",
        "rtsp_url": "rtsp://username:password@192.168.1.101:554/stream",
        "username": "",
        "password": "",
        "location": "MG Road Junction - North Approach",
        "description": "Main signal junction, covers both two-wheeler lanes.",
        "allowed_direction": "LEFT_TO_RIGHT",
    },
    {
        "camera_id": "CAM-02",
        "name": "Camera 2",
        "ip_address": "192.168.1.102",
        "rtsp_url": "rtsp://username:password@192.168.1.102:554/stream",
        "username": "",
        "password": "",
        "location": "Ring Road Flyover - Service Lane",
        "description": "Service lane frequently used for wrong side driving.",
        "allowed_direction": "RIGHT_TO_LEFT",
    },
    {
        "camera_id": "CAM-03",
        "name": "Camera 3",
        "ip_address": "192.168.1.103",
        "rtsp_url": "rtsp://username:password@192.168.1.103:554/stream",
        "username": "",
        "password": "",
        "location": "Market Street - Bus Stand Entry",
        "description": "High two-wheeler density, helmet and triple riding checks.",
        "allowed_direction": "ANY",
    },
]

DEMO_VEHICLES = [
    {
        "plate_number": "KA05MJ2020",
        "owner_name": "Vinod Kumar",
        "owner_phone": "9000000011",
        "owner_address": "12, 4th Cross, Jayanagar",
        "vehicle_type": "Two Wheeler",
        "make_model": "Honda Activa 6G",
        "colour": "Grey",
    },
    {
        "plate_number": "TN09BX7788",
        "owner_name": "Lakshmi Narayanan",
        "owner_phone": "9000000012",
        "owner_address": "45, Anna Nagar East",
        "vehicle_type": "Two Wheeler",
        "make_model": "TVS Jupiter",
        "colour": "Blue",
    },
    {
        "plate_number": "MH12KL4521",
        "owner_name": "Sameer Patil",
        "owner_phone": "9000000013",
        "owner_address": "7, Kothrud, Pune",
        "vehicle_type": "Two Wheeler",
        "make_model": "Bajaj Pulsar 150",
        "colour": "Black",
    },
]


async def create_demo_users() -> int:
    created = 0
    for entry in DEMO_USERS:
        if await coll(USERS).find_one({"user_id": entry["user_id"]}):
            continue
        await coll(USERS).insert_one(
            {
                "user_id": entry["user_id"],
                "name": entry["name"],
                "role": entry["role"],
                "designation": entry["designation"],
                "phone": entry["phone"],
                "email": entry["email"],
                "station": entry["station"],
                "active": True,
                "password_hash": hash_password(entry["password"]),
                # Seeded demo accounts only: lets the login page show the demo
                # credentials in development builds. Real accounts never store this.
                "is_demo": True,
                "demo_password": entry["password"],
                "login_count": 0,
                "last_login_at": None,
                "created_at": utcnow_iso(),
                "created_by": "bootstrap",
                "updated_at": utcnow_iso(),
            }
        )
        created += 1
    return created


async def create_demo_cameras() -> int:
    created = 0
    for entry in DEMO_CAMERAS:
        if await coll(CAMERAS).find_one({"camera_id": entry["camera_id"]}):
            continue
        await coll(CAMERAS).insert_one(
            {
                **entry,
                # Starts in DEMO MODE so Live Monitoring works without hardware.
                # Switch a camera to LIVE from Admin -> Cameras once the real
                # IP camera is reachable on the network.
                "mode": MODE_DEMO,
                "demo_source_type": DEMO_SOURCE_SYNTHETIC,
                "demo_source_path": "",
                "enabled": True,
                "detection_enabled": True,
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
                "created_by": "bootstrap",
                "updated_at": utcnow_iso(),
            }
        )
        created += 1
    return created


async def create_demo_vehicles() -> int:
    created = 0
    for entry in DEMO_VEHICLES:
        if await coll(VEHICLES).find_one({"plate_number": entry["plate_number"]}):
            continue
        await coll(VEHICLES).insert_one(
            {
                **entry,
                "registration_date": "2021-06-15",
                "insurance_valid_till": "2027-03-31",
                "puc_valid_till": "2026-12-31",
                "source": "SEED",
                "violation_count": 0,
                "total_fine": 0.0,
                "total_paid": 0.0,
                "created_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
            }
        )
        created += 1
    return created


async def bootstrap_if_empty() -> dict:
    await ensure_rules()
    report = {
        "users_created": await create_demo_users(),
        "cameras_created": await create_demo_cameras(),
        "vehicles_created": await create_demo_vehicles(),
    }
    if any(report.values()):
        logger.info("Bootstrap created %s", report)
    return report
