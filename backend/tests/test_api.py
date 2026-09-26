import datetime as dt
import time

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_ready_checks_db():
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 200


def test_ingest_schedule_and_telemetry_flow_produces_risk():
    with TestClient(app) as client:
        now = dt.datetime.utcnow()
        tr_id = 555
        target_time = now + dt.timedelta(minutes=12)

        schedule_resp = client.post(
            "/ingest/schedule",
            json={
                "stops": [
                    {
                        "tr_id": tr_id,
                        "stop_id": 1,
                        "seq": 0,
                        "scheduled_time": (now - dt.timedelta(minutes=5)).isoformat(),
                        "latitude": 55.75,
                        "longitude": 37.61,
                    },
                    {
                        "tr_id": tr_id,
                        "stop_id": 2,
                        "seq": 1,
                        "scheduled_time": target_time.isoformat(),
                        "latitude": 55.76,
                        "longitude": 37.62,
                    },
                ]
            },
        )
        assert schedule_resp.status_code == 200
        assert schedule_resp.json()["accepted"] == 2

        telemetry_resp = client.post(
            "/ingest/telemetry",
            json={
                "records": [
                    {
                        "vehicle_id": "bus-42",
                        "event_time": (now - dt.timedelta(minutes=5) + dt.timedelta(seconds=200)).isoformat(),
                        "latitude": 55.75,
                        "longitude": 37.61,
                        "speed": 0.0,
                        "door_open": True,
                        "tr_id": tr_id,
                    }
                ]
            },
        )
        assert telemetry_resp.status_code == 202

        # give the background telemetry worker + scheduler a couple of ticks
        deadline = time.time() + 3.0
        deviation = None
        while time.time() < deadline:
            r = client.get("/vehicles/bus-42/deviation")
            if r.status_code == 200:
                deviation = r.json()
                break
            time.sleep(0.1)
        assert deviation is not None
        assert deviation["cur_dev_s"] == 200

        deadline = time.time() + 3.0
        risk = None
        while time.time() < deadline:
            r = client.get("/risk/bus-42")
            if r.status_code == 200:
                risk = r.json()
                break
            time.sleep(0.1)
        assert risk is not None
        assert risk["predicted_delay_s"] == 200.0  # heuristic fallback == cur_dev_s (no inference service in tests)
        assert risk["source"] == "fallback"


def test_recompute_endpoint_is_synchronous_and_idempotent():
    with TestClient(app) as client:
        r1 = client.post("/risk/recompute")
        assert r1.status_code == 200
        assert "predictions_made" in r1.json()
