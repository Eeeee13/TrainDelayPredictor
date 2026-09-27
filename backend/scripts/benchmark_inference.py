"""Measure real HTTP inference, including DB reads and feature preparation.

Supply a JSON array of real /predict items on stdin. Run from the backend
container with --url http://inference:8000/predict to measure its network path.
This calls ML directly, so backend fallback cannot disguise slow inference.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://inference:8000/predict")
    parser.add_argument("--sizes", default="1,10,23")
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    items = json.load(sys.stdin)
    sizes = [int(size) for size in args.sizes.split(",")]
    if args.repeats < 1 or not items or any(n < 1 or n > len(items) for n in sizes):
        parser.error("Require positive repeats and batch sizes within the input item count")
    report = {"measured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "url": args.url, "input_items": len(items),
              "scope": "sequential HTTP requests; running service; no warmup excluded; not cold start",
              "batches": []}
    for size in sizes:
        samples, errors, versions = [], [], set()
        for run in range(args.repeats):
            # Rotate vehicles to avoid testing only the same one; never duplicate
            # items within a batch. Construct a fresh client as the backend does.
            selected = [items[(run * size + j) % len(items)] for j in range(size)]
            try:
                with httpx.Client(timeout=30) as client:
                    started = time.perf_counter()
                    response = client.post(args.url, json={"items": selected})
                    elapsed = time.perf_counter() - started
                    response.raise_for_status()
                    output = response.json()["items"]
                    if (len(output) != size or
                            {r["request_id"] for r in output} != {r["request_id"] for r in selected}):
                        raise ValueError("Response does not match request items")
                    for row in output:
                        if not math.isfinite(row["predicted_delay_s"]):
                            raise ValueError("Non-finite model output")
                        versions.add(row["model_version"])
                    samples.append(elapsed)
            except Exception as exc:
                errors.append({"run": run, "error": str(exc)})
        ordered = sorted(samples)
        result = {"size": size, "requests": args.repeats, "successes": len(samples),
                  "errors": errors, "model_versions": sorted(versions),
                  "samples_s": samples, "over_2s": sum(s > 2 for s in samples)}
        if samples:
            result.update(first_s=samples[0], median_s=statistics.median(samples),
                          p95_s=ordered[math.ceil(len(ordered) * .95) - 1],
                          max_s=max(samples), mean_s=statistics.mean(samples))
        report["batches"].append(result)
        print(f"Batch {size}: {len(samples)}/{args.repeats} successful", file=sys.stderr, flush=True)
    print(json.dumps(report, indent=2))
    if any(b["errors"] or b["over_2s"] for b in report["batches"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
