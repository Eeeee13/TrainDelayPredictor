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
    parser.add_argument("--vehicle", type=int, help="replay one tr_id for a short demo")
    parser.add_argument("--max-points", type=int, help="stop after this many telemetry fixes")
    parser.add_argument("--start-at", type=dt.datetime.fromisoformat,
                        help="first CSV event time, e.g. 2026-01-06T17:45:00")
    parser.add_argument("--end-at", type=dt.datetime.fromisoformat,
                        help="last CSV event time, e.g. 2026-01-06T18:25:00")
    parser.add_argument("--pause-at-end", action="store_true",
                        help="freeze virtual time after replay so the last map frame stays visible")
    args = parser.parse_args()

    if args.start_at and args.end_at and args.start_at > args.end_at:
        parser.error("--start-at must not be later than --end-at")

    schedule = [s for s in read_schedule_csv(args.schedule) if args.vehicle is None or s.tr_id == args.vehicle]
    telemetry = sorted((t for t in read_traffic_csv(args.traffic)
                        if (args.vehicle is None or t.tr_id == args.vehicle)
                        and (args.start_at is None or t.event_time >= args.start_at)
                        and (args.end_at is None or t.event_time <= args.end_at)),
                       key=lambda t: t.event_time)
    if args.max_points is not None:
        telemetry = telemetry[:args.max_points]
    if not telemetry:
        print("no telemetry rows found")
        return

    dataset_start = telemetry[0].event_time

    client = httpx.Client(timeout=10)
    r = client.post(f"{args.backend}/ingest/replay-clock", json={"start": dataset_start.isoformat(), "speed": args.speed})
    r.raise_for_status()

    schedule_batch_size = 500
    for i in range(0, len(schedule), schedule_batch_size):
        batch = schedule[i:i + schedule_batch_size]
        schedule_payload = {
            "stops": [
                {
                    "tr_id": s.tr_id,
                    "stop_id": s.stop_id,
                    "seq": s.seq,
                    "scheduled_time": s.scheduled_time.isoformat(),
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "manual_fill": s.manual_fill,
                }
                for s in batch
            ]
        }
        r = client.post(f"{args.backend}/ingest/schedule", json=schedule_payload)
        r.raise_for_status()
        print(f"schedule ingested batch {i//schedule_batch_size + 1}: {r.json()}")

    batch: list[dict] = []
    last_event_time = telemetry[0].event_time
    last_flush_wall = time.monotonic()
    flush_interval_s = 2.0
    for record in telemetry:
        wait_s = (record.event_time - last_event_time).total_seconds() / args.speed
        if wait_s > 0:
            time.sleep(min(wait_s, 5.0))  # cap so a data gap doesn't stall the demo for real minutes
        last_event_time = record.event_time

        batch.append(
            {
                "vehicle_id": record.vehicle_id,
                "event_time": record.event_time.isoformat(),
                "latitude": record.latitude,
                "longitude": record.longitude,
                "speed": record.speed,
                "door_open": record.door_open,
                "tr_id": record.tr_id,
                "location_valid": record.location_valid,
            }
        )
        now_wall = time.monotonic()
        if len(batch) >= args.batch_size or (batch and now_wall - last_flush_wall >= flush_interval_s):
            client.post(f"{args.backend}/ingest/telemetry", json={"records": batch}).raise_for_status()
            print(f"telemetry flushed: {len(batch)} points (last event_time={last_event_time.isoformat()})")
            batch.clear()
            last_flush_wall = now_wall

    if batch:
        client.post(f"{args.backend}/ingest/telemetry", json={"records": batch}).raise_for_status()
        print(f"telemetry flushed: {len(batch)} points (final)")

    if args.pause_at_end:
        time.sleep(2)  # let the asynchronous telemetry worker drain the final batch
        client.post(f"{args.backend}/ingest/replay-clock/pause").raise_for_status()

    print("replay complete")


if __name__ == "__main__":
    main()
