from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class TelemetryRecordIn(BaseModel):
    vehicle_id: str
    event_time: dt.datetime
    latitude: float
    longitude: float
    speed: float = 0.0
    door_open: bool = False
    tr_id: int | None = None
    location_valid: bool = True


class TelemetryBatchIn(BaseModel):
    records: list[TelemetryRecordIn]


class ScheduleStopIn(BaseModel):
    tr_id: int
    stop_id: int
    seq: int
    scheduled_time: dt.datetime
    latitude: float | None = None
    longitude: float | None = None
    manual_fill: bool = False


class ScheduleBatchIn(BaseModel):
    stops: list[ScheduleStopIn]
    route_id: str | None = None
    vehicle_id: str | None = None


class IngestAck(BaseModel):
    accepted: int


class RiskAssessmentOut(BaseModel):
    vehicle_id: str
    tr_id: int
    target_stop_id: int
    target_time_begin: dt.datetime
    predicted_at: dt.datetime
    predicted_delay_s: float
    risk_level: str
    reason: str
    source: str
    confidence: float | None = None
    delay_probability: float | None = Field(default=None, ge=0, le=1, description="Probability of delay strictly greater than 120 seconds at the target stop.")


class VehicleDeviationOut(BaseModel):
    vehicle_id: str
    tr_id: int | None
    cur_dev_s: int
    last_matched_stop_id: int | None
    avg_speed_segment: float
    last_event_time: dt.datetime | None
    is_stationary: bool


class RecomputeResult(BaseModel):
    predictions_made: int = Field(description="number of RiskAssessments (re)computed in this pass")
