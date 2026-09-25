"""Quick end-to-end demo for the jury: seeds one trip whose next stop is
already inside the 10-15 minute forecast window, so a risk assessment
appears (via `GET /risk` and the `/ws/risk` websocket) within one
scheduler tick (~5s) of running this script - no need to wait out a full
simulated route.

Usage:
    python -m scripts.seed_demo --backend http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument("--tr-id", type=int, default=131672)
    parser.add_argument("--vehicle-id", default="bus-101")
    parser.add_argument("--delay-s", type=int, default=280, help="how late the vehicle currently is")
    args = parser.parse_args()

    now = dt.datetime.utcnow()
    passed_stop_scheduled = now - dt.timedelta(minutes=8)
    passed_stop_actual = passed_stop_scheduled + dt.timedelta(seconds=args.delay_s)
    target_stop_scheduled = now + dt.timedelta(minutes=12)  # inside the [10,15] min window right away

    stop_id_passed = args.tr_id * 1000
    stop_id_target = args.tr_id * 1000 + 1

    client = httpx.Client(timeout=10)

    schedule_payload = {
        "route_id": "demo-route",
        "vehicle_id": args.vehicle_id,
        "stops": [
            {
                "tr_id": args.tr_id,
                "stop_id": stop_id_passed,
                "seq": 0,
                "scheduled_time": passed_stop_scheduled.isoformat(),
                "latitude": 55.751244,
                "longitude": 37.618423,
            },
            {
                "tr_id": args.tr_id,
                "stop_id": stop_id_target,
                "seq": 1,
                "scheduled_time": target_stop_scheduled.isoformat(),
                "latitude": 55.755244,
                "longitude": 37.622423,
            },
        ],
    }
    r = client.post(f"{args.backend}/ingest/schedule", json=schedule_payload)
    r.raise_for_status()
    print("schedule ingested:", r.json())

    telemetry_payload = {
        "records": [
            {
                "vehicle_id": args.vehicle_id,
                "event_time": passed_stop_actual.isoformat(),
                "latitude": 55.751244,
                "longitude": 37.618423,
                "speed": 0.0,
                "door_open": True,
                "tr_id": args.tr_id,
            }
        ]
    }
    r = client.post(f"{args.backend}/ingest/telemetry", json=telemetry_payload)
    r.raise_for_status()
    print("telemetry ingested:", r.json())

    print(
        f"\nSeeded {args.vehicle_id} on trip {args.tr_id}, currently {args.delay_s}s behind schedule, "
        f"next stop {stop_id_target} due at {target_stop_scheduled.isoformat()}Z (~12 min out).\n"
        "Wait a few seconds and check:\n"
        f"  GET {args.backend}/risk\n"
        f"  GET {args.backend}/vehicles/{args.vehicle_id}/deviation\n"
        f"  ws {args.backend.replace('http', 'ws')}/ws/risk\n"
    )


if __name__ == "__main__":
    main()
