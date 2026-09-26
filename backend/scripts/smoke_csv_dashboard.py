"""Replay a real CSV interval and verify the backend -> ML -> dashboard chain.

Run inside the backend container on the Compose network. Exits non-zero if the
model did not produce a horizon-compliant prediction visible to the frontend.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time

import httpx


def _seconds_between(later: str, earlier: str) -> float:
    return (dt.datetime.fromisoformat(later) - dt.datetime.fromisoformat(earlier)).total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--traffic", required=True)
    parser.add_argument("--vehicle", type=int, required=True)
    parser.add_argument("--start-at", required=True)
    parser.add_argument("--end-at", required=True)
    parser.add_argument("--speed", type=float, default=60)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument("--frontend", default="http://frontend")
    parser.add_argument("--verify-timeout", type=float, default=30)
    args = parser.parse_args()

    replay = [
        sys.executable, "-m", "scripts.replay_csv",
        "--schedule", args.schedule,
        "--traffic", args.traffic,
        "--vehicle", str(args.vehicle),
        "--start-at", args.start_at,
        "--end-at", args.end_at,
        "--speed", str(args.speed),
        "--batch-size", str(args.batch_size),
        "--backend", args.backend,
        "--pause-at-end",
    ]
    subprocess.run(replay, check=True)

    deadline = time.monotonic() + args.verify_timeout
    last_error = "No prediction yet"
    with httpx.Client(timeout=8) as client:
        while time.monotonic() < deadline:
            try:
                risk_response = client.get(f"{args.backend}/risk/{args.vehicle}")
                if risk_response.status_code != 200:
                    last_error = f"Risk API: HTTP {risk_response.status_code}"
                    time.sleep(1)
                    continue
                risk = risk_response.json()
                if risk["source"] != "model":
                    last_error = f"Inference fell back to {risk['source']}"
                    time.sleep(1)
                    continue
                probability = risk.get("delay_probability")
                if probability is None or not 0 <= probability <= 1:
                    last_error = "Calibrated probability missing or invalid"
                    time.sleep(1)
                    continue
                lead_s = _seconds_between(risk["target_time_begin"], risk["predicted_at"])
                if not 600 < lead_s <= 900:
                    last_error = f"Forecast horizon outside (10, 15] minutes: {lead_s:.1f}s"
                    time.sleep(1)
                    continue
                response = client.get(f"{args.frontend}/dashboard/snapshot")
                response.raise_for_status()
                snapshot = response.json()
                vehicle = next((v for v in snapshot["vehicles"] if v["vehicle_id"] == str(args.vehicle)), None)
                route = next((r for r in snapshot["routes"] if r["vehicle_id"] == str(args.vehicle)), None)
                if vehicle is None or route is None or vehicle["risk"] is None:
                    last_error = "Prediction or route absent from frontend snapshot"
                    time.sleep(1)
                    continue
                if len(vehicle["trail"]) < 2:
                    last_error = "Too few valid GPS points for the map trail"
                    time.sleep(1)
                    continue
                if not any(s["id"] == str(risk["target_stop_id"]) for s in route["stops"]):
                    last_error = "Target stop absent from frontend route window"
                    time.sleep(1)
                    continue
                report = {
                    "status": "passed",
                    "vehicle_id": vehicle["vehicle_id"],
                    "gps_points_on_map": len(vehicle["trail"]),
                    "route_stops_on_map": len(route["stops"]),
                    "risk_level": risk["risk_level"],
                    "predicted_delay_s": risk["predicted_delay_s"],
                    "delay_probability": probability,
                    "prediction_source": risk["source"],
                    "lead_time_s": round(lead_s, 1),
                    "highlight_expected": risk["risk_level"] in ("medium", "high"),
                }
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(1)
    raise SystemExit(f"CSV dashboard smoke test failed: {last_error}")


if __name__ == "__main__":
    main()
