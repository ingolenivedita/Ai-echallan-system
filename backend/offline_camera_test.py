"""Check the camera health / maintenance alert path.

Registers a LIVE camera pointing at an unroutable RTSP address, waits for the
capture thread to fail, and confirms that:

* the failing camera is reported OFFLINE with a connection error,
* a maintenance alert is raised for it,
* the existing demo cameras keep streaming (independent per-camera threads).

The temporary camera is deleted again at the end.
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
CAMERA_ID = "CAM-OFFLINE-TEST"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=90.0) as client:
        login = client.post(
            "/api/auth/login", json={"user_id": "ADMIN001", "password": "Admin@123"}
        )
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        healthy_before = {
            camera["camera_id"]: camera.get("status")
            for camera in client.get("/api/cameras/health/all").json()["cameras"]
        }
        print(f"before: {healthy_before}")

        created = client.post(
            "/api/cameras",
            json={
                "camera_id": CAMERA_ID,
                "name": "Unreachable Test Camera",
                "ip_address": "192.0.2.10",
                "rtsp_url": "rtsp://192.0.2.10:554/stream",
                "location": "Offline path test",
                "description": "Created by offline_camera_test.py",
                "mode": "LIVE",
                "enabled": True,
            },
        )
        print(f"{created.status_code}  POST /api/cameras ({CAMERA_ID})")
        if created.status_code >= 300:
            print(created.text)
            return 1

        try:
            status = ""
            error = ""
            others: dict[str, str] = {}
            mine: list[dict] = []

            # The capture thread needs an RTSP timeout to elapse, and the alert
            # is written by the camera sync loop on its next pass.
            for _ in range(30):
                time.sleep(5)
                health = client.get("/api/cameras/health/all").json()["cameras"]
                entry = next((c for c in health if c["camera_id"] == CAMERA_ID), {})
                status = entry.get("status", "")
                error = entry.get("connection_error", "")
                others = {
                    c["camera_id"]: c.get("status")
                    for c in health
                    if c["camera_id"] != CAMERA_ID
                }
                alerts = client.get("/api/alerts?status=OPEN").json()["alerts"]
                mine = [a for a in alerts if a.get("camera_id") == CAMERA_ID]
                print(f"  {CAMERA_ID}={status!r} error={error[:70]!r} "
                      f"alerts={len(mine)} others={others}")
                if status == "OFFLINE" and mine:
                    break

            for alert in mine:
                print(f"  alert: {alert.get('message')} | {alert.get('detail')}")

            still_streaming = bool(others) and all(
                value == "ONLINE" for value in others.values()
            )
            print(f"other cameras still ONLINE: {still_streaming}")

            ok = status == "OFFLINE" and bool(mine) and bool(error) and still_streaming
            print("\nPASS" if ok else "\nFAIL")
            return 0 if ok else 1
        finally:
            removed = client.delete(f"/api/cameras/{CAMERA_ID}")
            print(f"{removed.status_code}  DELETE /api/cameras/{CAMERA_ID}")
            client.delete("/api/alerts/clear-resolved")


if __name__ == "__main__":
    sys.exit(main())
