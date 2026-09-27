"""Domain layer: plain dataclasses, no FastAPI/SQLAlchemy imports here.
This is what gets passed between MatchingEngine -> FeatureBuilder ->
InferenceClient -> RiskAggregator, so it has to stay stable and cheap to
construct (these objects are built once per NDTP packet, per vehicle).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PredictionSource(str, Enum):
    MODEL = "model"
    FALLBACK = "fallback"


@dataclass(slots=True, frozen=True)
class TelemetryRecord:
    """One normalized NDTP-derived telemetry point."""

    vehicle_id: str
    event_time: datetime
    latitude: float
    longitude: float
    speed: float
    door_open: bool = False
    tr_id: int | None = None  # trip id, if the source already resolved it
    location_valid: bool = True


@dataclass(slots=True, frozen=True)
class ScheduleStop:
    """One stop on a scheduled trip (the reference timetable)."""

    tr_id: int
    stop_id: int
    seq: int
    scheduled_time: datetime
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    manual_fill: bool = False


@dataclass(slots=True)
class VehicleState:
    """In-memory, per-vehicle rolling state maintained by the MatchingEngine.

    This is the hot path object: rebuilt/updated on every NDTP packet
    (~12-15s) and read by the PredictionScheduler on every tick. Kept
    entirely in memory for latency; DB is for durability/audit only.
    """

    vehicle_id: str
    tr_id: int | None = None
    last_event_time: datetime | None = None
    last_lat: float | None = None
    last_lon: float | None = None
    last_speed: float | None = None
    cur_dev_s: int = 0
    last_matched_stop_id: int | None = None
    last_matched_seq: int = -1
    avg_speed_segment: float = 0.0
    stationary_since: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class PredictItem:
    """Exact payload shape the ML model expects (matches
    `predictor.predict(tr_id, T, cur_dev_s, target_stop_id, target_time_begin)`).
    """

    request_id: str
    tr_id: int
    T: datetime
    cur_dev_s: int
    target_stop_id: int
    target_time_begin: datetime


@dataclass(slots=True, frozen=True)
class PredictResult:
    request_id: str
    predicted_delay_s: float
    confidence: float | None
    source: PredictionSource
    model_version: str | None = None
    delay_probability: float | None = None


@dataclass(slots=True, frozen=True)
class RiskAssessment:
    vehicle_id: str
    tr_id: int
    target_stop_id: int
    target_time_begin: datetime
    predicted_at: datetime
    predicted_delay_s: float
    risk_level: RiskLevel
    reason: str
    source: PredictionSource
    confidence: float | None = None
    delay_probability: float | None = None

    def to_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id,
            "tr_id": self.tr_id,
            "target_stop_id": self.target_stop_id,
            "target_time_begin": self.target_time_begin.isoformat(),
            "predicted_at": self.predicted_at.isoformat(),
            "predicted_delay_s": self.predicted_delay_s,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
            "source": self.source.value,
            "confidence": self.confidence,
            "delay_probability": self.delay_probability,
        }
