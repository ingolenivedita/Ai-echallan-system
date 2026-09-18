"""End-to-end smoke test against a running backend.

Usage (with the backend already running on 127.0.0.1:8000):

    .venv\\Scripts\\python.exe smoke_test.py

It logs in as the demo administrator and walks every REST surface the frontend
uses, printing the HTTP status of each call. Any non-2xx response is reported at
the end as a failure so the whole API can be checked in one command.
"""

from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"

READ_ENDPOINTS = [
    "/api/health",
    "/api/auth/demo-credentials",
    "/api/dashboard/summary",
    "/api/cameras",
    "/api/cameras/CAM-01",
    "/api/violations?limit=5",
    "/api/violations/stats",
    "/api/challans?limit=5",
    "/api/challans/stats",
    "/api/vehicles?limit=5",
    "/api/reports/overview",
    "/api/reports/export/violations",
    "/api/reports/export/challans",
    "/api/config/status",
    "/api/config/sms/logs",
    "/api/network/status",
    "/api/alerts",
    "/api/rules",
    "/api/users",
    "/api/users/audit/log",
    "/api/settings",
    "/api/cameras/health/all",
    "/api/cameras/demo-media",
    "/api/payments",
]


def main() -> int:
    failures: list[str] = []
    leftovers: list[str] = []

    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        login = client.post(
            "/api/auth/login",
            json={"user_id": "ADMIN001", "password": "Admin@123"},
        )
        print(f"{login.status_code}  POST /api/auth/login")
        if login.status_code != 200:
            print(login.text)
            return 1
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        for path in READ_ENDPOINTS:
            response = client.get(path)
            print(f"{response.status_code}  GET  {path}  ({len(response.content)} bytes)")
            if response.status_code >= 300:
                failures.append(f"GET {path} -> {response.status_code} {response.text[:200]}")

        # Camera connection test, snapshot and a one-off detection pass.
        for method, path, payload in [
            ("POST", "/api/cameras/CAM-01/test", None),
            ("POST", "/api/cameras/CAM-01/detect-now", None),
            ("POST", "/api/config/test/ai", None),
            ("POST", "/api/config/test/anpr", None),
            ("POST", "/api/config/test/sms", None),
            ("POST", "/api/config/test/payment", None),
            ("POST", "/api/network/refresh-cameras", None),
            ("POST", "/api/reports/ai-summary", {"days": 7}),
        ]:
            response = client.request(method, path, json=payload)
            print(f"{response.status_code}  {method} {path}")
            if response.status_code >= 300:
                failures.append(f"{method} {path} -> {response.status_code} {response.text[:200]}")

        snapshot = client.get("/api/cameras/CAM-01/snapshot")
        print(f"{snapshot.status_code}  GET  /api/cameras/CAM-01/snapshot "
              f"({len(snapshot.content)} bytes, {snapshot.headers.get('content-type')})")
        if snapshot.status_code != 200 or not snapshot.content:
            failures.append("camera snapshot returned no image")

        # A registered vehicle with an owner number, so the SMS notice has a
        # recipient. Registered here rather than reusing seed data so repeated
        # runs never touch the demo dataset.
        plate = "KA01SMK0001"
        created_vehicle = client.post(
            "/api/vehicles",
            json={
                "plate_number": plate,
                "owner_name": "Smoke Test Owner",
                "owner_phone": "9000000099",
                "owner_address": "RTO test record",
                "vehicle_type": "Two Wheeler",
            },
        )
        print(f"{created_vehicle.status_code}  POST /api/vehicles ({plate})")
        if created_vehicle.status_code >= 300 and created_vehicle.status_code != 409:
            failures.append(
                f"vehicle -> {created_vehicle.status_code} {created_vehicle.text[:200]}"
            )

        # Enforcement walkthrough run twice: once paid, once cancelled, so both
        # the payment path and the delete path are covered.
        for index, settle in enumerate(("pay", "delete"), start=1):
            manual = client.post(
                "/api/violations/manual",
                json={
                    "camera_id": "CAM-01",
                    "violation_type": "NO_HELMET",
                    "plate_number": plate,
                    "confidence": 0.97,
                    "remarks": f"Created by smoke_test.py (run {index})",
                },
            )
            print(f"{manual.status_code}  POST /api/violations/manual")
            if manual.status_code >= 300:
                failures.append(f"manual violation -> {manual.status_code} {manual.text[:200]}")
                continue
            violation_id = manual.json()["violation"]["id"]

            challan = client.post(
                "/api/challans", json={"violation_id": violation_id, "send_sms": True}
            )
            print(f"{challan.status_code}  POST /api/challans")
            if challan.status_code >= 300:
                failures.append(f"challan -> {challan.status_code} {challan.text[:200]}")
                client.delete(f"/api/violations/{violation_id}")
                continue
            challan_id = challan.json()["challan"]["id"]

            resend = client.post(f"/api/challans/{challan_id}/resend-sms")
            print(f"{resend.status_code}  POST /api/challans/{{id}}/resend-sms")
            if resend.status_code >= 300:
                failures.append(f"resend sms -> {resend.status_code} {resend.text[:200]}")

            order = client.post("/api/payments/create-order", json={"challan_id": challan_id})
            print(f"{order.status_code}  POST /api/payments/create-order "
                  f"(demo={order.json().get('demo')})")
            if order.status_code >= 300:
                failures.append(f"payment order -> {order.status_code} {order.text[:200]}")

            if settle == "pay":
                paid = client.post(
                    "/api/payments/offline",
                    json={"challan_id": challan_id},
                    params={"method": "CASH_COUNTER", "reference": "SMOKE-TEST"},
                )
                print(f"{paid.status_code}  POST /api/payments/offline")
                if paid.status_code >= 300:
                    failures.append(f"offline payment -> {paid.status_code} {paid.text[:200]}")
                else:
                    after = client.get(f"/api/challans/{challan_id}").json()
                    print(f"--   challan {after.get('challan_number')} "
                          f"status={after.get('status')}")
                    if after.get("status") != "PAID":
                        failures.append(f"challan not marked PAID (got {after.get('status')})")

                # A paid challan must stay on record.
                protected = client.delete(f"/api/challans/{challan_id}")
                print(f"{protected.status_code}  DELETE /api/challans/{{id}} (paid, expect 409)")
                if protected.status_code != 409:
                    failures.append(
                        f"paid challan was deletable -> {protected.status_code}"
                    )
                # A paid challan also cannot be cancelled - it stays in the
                # register as a permanent record, so the test leaves it behind.
                cancelled = client.patch(
                    f"/api/challans/{challan_id}/status",
                    json={"status": "CANCELLED", "remarks": "smoke test cleanup"},
                )
                print(f"{cancelled.status_code}  PATCH /api/challans/{{id}}/status "
                      f"-> CANCELLED (paid, expect 409)")
                if cancelled.status_code != 409:
                    failures.append(
                        f"paid challan was cancellable -> {cancelled.status_code}"
                    )
                leftovers.append(
                    client.get(f"/api/challans/{challan_id}").json().get("challan_number", "")
                )
            else:
                removed = client.delete(f"/api/challans/{challan_id}")
                print(f"{removed.status_code}  DELETE /api/challans/{{id}} (pending)")
                if removed.status_code >= 300:
                    failures.append(
                        f"delete pending challan -> {removed.status_code} {removed.text[:200]}"
                    )

            removed = client.delete(f"/api/violations/{violation_id}")
            print(f"{removed.status_code}  DELETE /api/violations/{{id}}")

        removed = client.delete(f"/api/vehicles/{plate}")
        print(f"{removed.status_code}  DELETE /api/vehicles/{plate}")

    print()
    if leftovers:
        print("Paid challans cannot be deleted, so these test records stay in the")
        print(f"register: {', '.join(filter(None, leftovers))}")
        print("Run 'python seed.py --reset' for a clean demo dataset.\n")
    if failures:
        print(f"FAILED ({len(failures)})")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
