"""Replays the hackathon dataset's traffic.csv/schedule.csv against a
running backend, time-shifted so the dataset's "now" lines up with the
real current time (otherwise every scheduled stop would be in the past
and nothing would ever enter the 10-15 minute forecast window).

Usage:
    python -m scripts.replay_csv --traffic traffic.csv --schedule schedule.csv \
        --backend http://localhost:8000 --speed 30
"""
from __future__ import annotations

import argparse
import datetime as dt
import time

import httpx

from app.adapters.csv_telemetry_adapter import read_schedule_csv, read_traffic_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traffic", required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument("--speed", type=float, default=30.0, help="playback speed multiplier")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    schedule = list(read_schedule_csv(args.schedule))
    telemetry = sorted(read_traffic_csv(args.traffic), key=lambda t: t.event_time)
    if not telemetry:
        print("no telemetry rows found")
        return

    dataset_start = telemetry[0].event_time
    offset = dt.datetime.utcnow() - dataset_start + dt.timedelta(minutes=1)

    client = httpx.Client(timeout=10)

    schedule_payload = {
        "stops": [
            {
                "tr_id": s.tr_id,
                "stop_id": s.stop_id,
                "seq": s.seq,
                "scheduled_time": (s.scheduled_time + offset).isoformat(),
                "latitude": s.latitude,
                "longitude": s.longitude,
            }
            for s in schedule
        ]
    }
    r = client.post(f"{args.backend}/ingest/schedule", json=schedule_payload)
    r.raise_for_status()
    print(f"schedule ingested: {r.json()}")

    batch: list[dict] = []
    last_event_time = telemetry[0].event_time
    for record in telemetry:
        wait_s = (record.event_time - last_event_time).total_seconds() / args.speed
        if wait_s > 0:
            time.sleep(min(wait_s, 5.0))  # cap so a data gap doesn't stall the demo for real minutes
        last_event_time = record.event_time

        batch.append(
            {
                "vehicle_id": record.vehicle_id,
                "event_time": (record.event_time + offset).isoformat(),
                "latitude": record.latitude,
                "longitude": record.longitude,
                "speed": record.speed,
                "door_open": record.door_open,
                "tr_id": record.tr_id,
            }
        )
        if len(batch) >= args.batch_size:
            client.post(f"{args.backend}/ingest/telemetry", json={"records": batch})
            batch.clear()

    if batch:
        client.post(f"{args.backend}/ingest/telemetry", json={"records": batch})

    print("replay complete")


if __name__ == "__main__":
    main()
