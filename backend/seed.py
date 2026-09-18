"""Seed script - demo accounts, three cameras, and optional sample activity.

    python seed.py                 # accounts + cameras + rules + vehicles
    python seed.py --violations 30 # also generate 30 past violations + challans
    python seed.py --reset         # wipe activity data first (keeps nothing)

Run it from the ``backend`` folder with the virtual environment active.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import timedelta

from app.bootstrap import bootstrap_if_empty
from app.constants import (
    CHALLAN_PAID,
    VIOLATION_APPROVED,
    VIOLATION_LABELS,
    VIOLATION_PENDING,
    VIOLATION_TYPES,
)
from app.database import (
    ALERTS,
    CAMERAS,
    CHALLANS,
    PAYMENTS,
    SMS_LOGS,
    VIOLATIONS,
    coll,
    database,
)
from app.services.challan_service import issue_challan
from app.services.detection_service import save_evidence
from app.services.synthetic import SyntheticTrafficSource
from app.utils import iso, utcnow, utcnow_iso

ACTIVITY_COLLECTIONS = [VIOLATIONS, CHALLANS, PAYMENTS, ALERTS, SMS_LOGS]


async def reset_activity() -> None:
    for name in ACTIVITY_COLLECTIONS:
        outcome = await coll(name).delete_many({})
        print(f"  cleared {name}: {outcome.deleted_count} document(s)")


async def generate_activity(count: int) -> None:
    cameras = await coll(CAMERAS).find({}).to_list(50)
    if not cameras:
        print("  no cameras found - run bootstrap first")
        return

    source = SyntheticTrafficSource()
    plates = [
        document.get("plate_number")
        for document in await coll("vehicles").find({}).to_list(50)
    ] or ["KA05MJ2020"]

    created_violations = 0
    created_challans = 0
    paid = 0

    for index in range(count):
        camera = random.choice(cameras)
        violation_type = random.choice(VIOLATION_TYPES)
        moment = utcnow() - timedelta(
            days=random.randint(0, 6), hours=random.randint(0, 23), minutes=random.randint(0, 59)
        )
        confidence = round(random.uniform(0.62, 0.97), 3)

        frame, _ = source.read()
        for _ in range(random.randint(3, 12)):
            frame, _ = source.read()

        detection = {
            "violation_type": violation_type,
            "confidence": confidence,
            "box": [random.randint(60, 500), random.randint(220, 380), 120, 90],
            "reason": "Seeded sample record for demonstration",
        }
        evidence = save_evidence(frame, [detection], camera)

        plate = random.choice(plates) if random.random() < 0.6 else _random_plate()
        document = {
            "camera_id": camera.get("camera_id"),
            "camera_name": camera.get("name", ""),
            "location": camera.get("location", ""),
            "violation_type": violation_type,
            "violation_label": VIOLATION_LABELS.get(violation_type, violation_type),
            "confidence": confidence,
            "detector": "DEMO_SIMULATOR",
            "simulated": True,
            "reason": detection["reason"],
            "box": detection["box"],
            "plate_number": plate,
            "plate_source": "SIMULATED",
            "vehicle_type": "two wheeler",
            "evidence_image": evidence,
            "detected_at": iso(moment),
            "status": VIOLATION_PENDING,
            "source": "SEED",
            "reviewed_by": "",
            "created_at": iso(moment),
            "updated_at": iso(moment),
        }
        inserted = await coll(VIOLATIONS).insert_one(document)
        document["_id"] = inserted.inserted_id
        created_violations += 1

        if random.random() < 0.7:
            await coll(VIOLATIONS).update_one(
                {"_id": inserted.inserted_id},
                {"$set": {"status": VIOLATION_APPROVED, "reviewed_by": "OFFICER001"}},
            )
            outcome = await issue_challan(document, actor="SEED", send_sms=False)
            if outcome["created"]:
                created_challans += 1
                challan_id = outcome["challan"]["id"]
                await coll(CHALLANS).update_one(
                    {"_id": challan_id},
                    {"$set": {"issued_at": iso(moment + timedelta(minutes=4))}},
                )
                if random.random() < 0.45:
                    amount = float(outcome["challan"]["fine_amount"])
                    await coll(CHALLANS).update_one(
                        {"_id": challan_id},
                        {
                            "$set": {
                                "status": CHALLAN_PAID,
                                "amount_paid": amount,
                                "paid_at": iso(moment + timedelta(hours=random.randint(2, 40))),
                                "paid_via": random.choice(["razorpay", "CASH_COUNTER"]),
                                "payment": {"mode": "DEMO", "method": "seed"},
                            }
                        },
                    )
                    await coll(PAYMENTS).insert_one(
                        {
                            "challan_id": challan_id,
                            "challan_number": outcome["challan"]["challan_number"],
                            "amount": amount,
                            "gateway": "seed",
                            "mode": "DEMO",
                            "status": "COLLECTED",
                            "configured": False,
                            "detail": "Seeded sample payment",
                            "created_by": "SEED",
                            "created_at": iso(moment + timedelta(hours=3)),
                        }
                    )
                    paid += 1

        if (index + 1) % 10 == 0:
            print(f"  generated {index + 1}/{count}")

    print(
        f"  violations: {created_violations}, challans: {created_challans}, paid: {paid}"
    )


def _random_plate() -> str:
    states = ["KA", "TN", "MH", "AP", "KL", "TS"]
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return (
        f"{random.choice(states)}{random.randint(10, 99)}"
        f"{random.choice(letters)}{random.choice(letters)}{random.randint(1000, 9999)}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the RTO E-Challan database")
    parser.add_argument(
        "--violations", type=int, default=0, help="number of sample violations to create"
    )
    parser.add_argument(
        "--reset", action="store_true", help="delete existing violations/challans first"
    )
    arguments = parser.parse_args()

    await database.connect()
    print(f"Database backend: {database.backend}")

    if arguments.reset:
        print("Clearing activity data...")
        await reset_activity()

    print("Bootstrapping accounts, cameras, rules and vehicles...")
    report = await bootstrap_if_empty()
    print(f"  {report}")

    if arguments.violations:
        print(f"Generating {arguments.violations} sample violations...")
        await generate_activity(arguments.violations)

    print("\nDemo credentials")
    print("  Administrator   : ADMIN001    / Admin@123")
    print("  Traffic Officer : OFFICER001  / Officer@123")
    print("  Traffic Officer : OFFICER002  / Officer@123")
    print(f"\nDone at {utcnow_iso()}")
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
