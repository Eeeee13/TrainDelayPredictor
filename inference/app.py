"""Batch inference service using the existing LightGBM predictor."""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import uuid
import os
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from model import DelayPredictor
from inference.schedule_cache import ScheduleCache, read_schedule
from model.timing import current_timings, measure, measured_lock

logger = logging.getLogger("uvicorn.error")

MOSCOW = ZoneInfo("Europe/Moscow")
DB_URL = os.getenv("INFERENCE_DATABASE_URL", "postgresql+psycopg://inference_ro:inference_ro@postgres:5432/predictor")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))
DEFAULT_MODEL = Path(os.getenv("DEFAULT_MODEL", "/srv/model/model.txt"))
engine = create_engine(DB_URL, pool_pre_ping=True)
schedule_cache = ScheduleCache()
SCHEDULE_CACHE_ENABLED = os.getenv("SCHEDULE_CACHE_ENABLED", "true").lower() == "true"
app = FastAPI(title="delay-inference")
_lock = RLock()
_predictor: DelayPredictor | None = None
_version: str | None = None


class PredictItem(BaseModel):
    request_id: str
    tr_id: int
    T: dt.datetime
    cur_dev_s: float
    target_stop_id: int
    target_time_begin: dt.datetime


class PredictBatch(BaseModel):
    items: list[PredictItem]


class PredictOutputItem(BaseModel):
    request_id: str
    predicted_delay_s: float
    confidence: float | None = None
    delay_probability: float | None = Field(default=None, ge=0, le=1, description="Probability of delay strictly greater than 120 seconds at the target stop.")
    model_version: str


class PredictOutput(BaseModel):
    items: list[PredictOutputItem]


def _local_naive(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.timezone.utc).astimezone(MOSCOW).replace(tzinfo=None) if value.tzinfo is None else value.astimezone(MOSCOW).replace(tzinfo=None)


def _utc_naive(value: dt.datetime) -> dt.datetime:
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _active_path() -> tuple[Path, str]:
    pointer = MODEL_DIR / "active.json"
    if pointer.exists():
        meta = json.loads(pointer.read_text())
        candidate = MODEL_DIR / meta["version"] / "model.txt"
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate, meta["version"]
    return DEFAULT_MODEL, "bundled"


def _model() -> tuple[DelayPredictor, str]:
    global _predictor, _version
    with measured_lock(_lock, "model_lock_wait_ms"), measure("model_check_ms"):
        try:
            path, version = _active_path()
            if _predictor is None or version != _version:
                candidate = DelayPredictor(path)
                # Small batches do not benefit from taking every available CPU.
                candidate.model.params["num_threads"] = 1
                if candidate.probability is not None:
                    candidate.probability.classifier.params["num_threads"] = 1
                _predictor, _version = candidate, version
        except Exception:
            if _predictor is None:
                raise
        assert _predictor is not None and _version is not None
        return _predictor, _version


@app.on_event("startup")
def load_initial_model() -> None:
    # Load weights before accepting requests, outside the request timeout budget.
    _model()


def _inputs(items: list[PredictItem], use_cache: bool):
    tr_ids = sorted({i.tr_id for i in items})
    max_t = max(_utc_naive(i.T) for i in items)
    with measure("db_connect_ms"):
        conn = engine.connect().execution_options(isolation_level="REPEATABLE READ")
    try:
        # Bind parameters individually; the list is validated integers, never SQL text.
        params = {f"tr_{n}": tr for n, tr in enumerate(tr_ids)}
        slots = ",".join(f":tr_{n}" for n in range(len(tr_ids)))
        schedule = schedule_cache.get(conn) if use_cache else read_schedule(conn, tr_ids)
        with measure("db_traffic_ms"):
            traffic_rows = conn.execute(text(f"SELECT tr_id, event_time, location_valid, longitude AS lon, "
                                             f"latitude AS lat, speed FROM telemetry_records WHERE tr_id IN ({slots}) "
                                             f"AND event_time <= :max_t ORDER BY tr_id, event_time"),
                                        {**params, "max_t": max_t}).tuples().all()
    finally:
        with measure("db_release_ms"):
            conn.close()
    timings = current_timings.get()
    if timings is not None:
        timings["schedule_rows"] = len(schedule.frame)
        timings["traffic_rows"] = len(traffic_rows)
    with measure("frames_ms"):
        traffic = pd.DataFrame(traffic_rows, columns=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"])
        traffic["event_time"] = pd.to_datetime(traffic.event_time, utc=True).dt.tz_convert(MOSCOW).dt.tz_localize(None)
    return schedule, traffic


def _frames(items: list[PredictItem]) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Compatibility for offline diagnostics; this path intentionally bypasses cache.
    schedule, traffic = _inputs(items, use_cache=False)
    return schedule.frame, traffic


@app.get("/health")
def health() -> dict:
    try:
        _, version = _model()
        return {"status": "ok", "model_version": version}
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/model/info")
def model_info() -> dict:
    model, version = _model()
    return {"version": version, "features": model.model.feature_name(),
            "delay_probability_available": model.probability is not None, "delay_threshold_s": 120}


@app.post("/predict", response_model=PredictOutput)
def predict(batch: PredictBatch) -> dict:
    timings = {}
    token = current_timings.set(timings)
    started = time.perf_counter()
    outcome = "ok"
    try:
        return _predict(batch)
    except Exception as exc:
        outcome = type(exc).__name__
        raise
    finally:
        total_ms = (time.perf_counter() - started) * 1000
        measured_ms = sum(value for key, value in timings.items() if key.endswith("_ms") and not key.endswith("_detail_ms"))
        logger.info("inference_stages %s", json.dumps({
            "trace_id": uuid.uuid4().hex, "items": len(batch.items),
            "vehicles": len({i.tr_id for i in batch.items}), "outcome": outcome,
            "total_ms": total_ms, "other_ms": total_ms - measured_ms, **timings,
        }))
        current_timings.reset(token)


def _predict(batch: PredictBatch) -> dict:
    if not batch.items:
        return {"items": []}
    model, version = _model()
    schedule, traffic = _inputs(batch.items, use_cache=SCHEDULE_CACHE_ENABLED)
    if schedule.frame.empty:
        raise HTTPException(422, "no schedule for requested vehicles")
    known = schedule.known
    for item in batch.items:
        target_time = pd.Timestamp(_local_naive(item.target_time_begin))
        if (item.tr_id, item.target_stop_id, target_time) not in known:
            raise HTTPException(422, f"unknown target stop or time for request_id={item.request_id}")
        lead = (target_time - pd.Timestamp(_local_naive(item.T))).total_seconds()
        if not 600 < lead <= 900:
            raise HTTPException(422, f"target outside (T+10, T+15] for request_id={item.request_id}")
    # One lock prevents concurrent requests mutating the shared predictor buffers.
    with measured_lock(_lock, "predict_lock_wait_ms"):
        # Feature construction only reads these prepared frames.
        model.sched = schedule.by_trip
        with measure("set_telemetry_ms"):
            model.set_telemetry(traffic)
        points = pd.DataFrame([{
            "tr_id": i.tr_id, "T": _local_naive(i.T), "cur_dev_s": i.cur_dev_s,
            "target_stop_id": i.target_stop_id, "target_time_begin": _local_naive(i.target_time_begin),
        } for i in batch.items])
        values, probabilities = model.predict_points_with_probability(points)
    return {"items": [{"request_id": item.request_id, "predicted_delay_s": float(value),
                       "confidence": None, "model_version": version,
                       "delay_probability": None if probability is None else float(probability)}
                      for item, value, probability in zip(batch.items, values, probabilities)]}
