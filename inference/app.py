"""Batch inference service using the existing LightGBM predictor."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from model import DelayPredictor

MOSCOW = ZoneInfo("Europe/Moscow")
DB_URL = os.getenv("INFERENCE_DATABASE_URL", "postgresql+psycopg://inference_ro:inference_ro@postgres:5432/predictor")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models"))
DEFAULT_MODEL = Path(os.getenv("DEFAULT_MODEL", "/srv/model/model.txt"))
engine = create_engine(DB_URL, pool_pre_ping=True)
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
    with _lock:
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


def _frames(items: list[PredictItem]) -> tuple[pd.DataFrame, pd.DataFrame]:
    tr_ids = sorted({i.tr_id for i in items})
    max_t = max(_utc_naive(i.T) for i in items)
    with engine.connect() as conn:
        # Bind parameters individually; the list is validated integers, never SQL text.
        params = {f"tr_{n}": tr for n, tr in enumerate(tr_ids)}
        slots = ",".join(f":tr_{n}" for n in range(len(tr_ids)))
        schedule_rows = conn.execute(text(f"SELECT tr_id, stop_id AS tt_action_item_id, scheduled_time AS time_begin, "
                                          f"longitude, latitude, manual_fill FROM schedule_stops WHERE tr_id IN ({slots})"),
                                     params).mappings().all()
        traffic_rows = conn.execute(text(f"SELECT tr_id, event_time, location_valid, longitude AS lon, "
                                         f"latitude AS lat, speed FROM telemetry_records WHERE tr_id IN ({slots}) "
                                         f"AND event_time <= :max_t ORDER BY tr_id, event_time"),
                                    {**params, "max_t": max_t}).mappings().all()
    schedule = pd.DataFrame(schedule_rows, columns=["tr_id", "tt_action_item_id", "time_begin",
                                                    "longitude", "latitude", "manual_fill"])
    traffic = pd.DataFrame(traffic_rows, columns=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"])
    schedule["time_begin"] = pd.to_datetime(schedule.time_begin, utc=True).dt.tz_convert(MOSCOW).dt.tz_localize(None)
    traffic["event_time"] = pd.to_datetime(traffic.event_time, utc=True).dt.tz_convert(MOSCOW).dt.tz_localize(None)
    schedule["geom"] = schedule.apply(lambda r: f"POINT ({r.longitude} {r.latitude})", axis=1)
    return schedule, traffic


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
    if not batch.items:
        return {"items": []}
    model, version = _model()
    schedule, traffic = _frames(batch.items)
    if schedule.empty:
        raise HTTPException(422, "no schedule for requested vehicles")
    known = set(zip(schedule.tr_id.astype(int), schedule.tt_action_item_id.astype(int), schedule.time_begin))
    for item in batch.items:
        target_time = pd.Timestamp(_local_naive(item.target_time_begin))
        if (item.tr_id, item.target_stop_id, target_time) not in known:
            raise HTTPException(422, f"unknown target stop or time for request_id={item.request_id}")
        lead = (target_time - pd.Timestamp(_local_naive(item.T))).total_seconds()
        if not 600 < lead <= 900:
            raise HTTPException(422, f"target outside (T+10, T+15] for request_id={item.request_id}")
    # One lock prevents concurrent requests mutating the shared predictor buffers.
    with _lock:
        model.load_schedule(schedule)
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
