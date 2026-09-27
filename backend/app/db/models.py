"""ORM models. Kept intentionally flat (no inheritance tricks) — these are
persistence/audit records, not domain objects; the domain lives in
app/domain/entities.py and never imports from here.

Portable across Postgres (prod) and SQLite (tests): no JSONB/ARRAY types.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelemetryRecordORM(Base):
    __tablename__ = "telemetry_records"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "event_time", name="uq_telemetry_vehicle_time"),
        Index("ix_telemetry_vehicle_time", "vehicle_id", "event_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    door_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tr_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ScheduleStopORM(Base):
    __tablename__ = "schedule_stops"
    __table_args__ = (
        UniqueConstraint("tr_id", "stop_id", name="uq_schedule_trip_stop"),
        Index("ix_schedule_tr_seq", "tr_id", "seq"),
        Index("ix_schedule_scheduled_time", "scheduled_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_time: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manual_fill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RiskAssessmentORM(Base):
    """Latest known risk per (tr_id, target_stop_id) — the row the
    scheduler upserts. This is what a dashboard's initial REST load reads;
    live updates come over the websocket instead.
    """

    __tablename__ = "risk_assessments"
    __table_args__ = (UniqueConstraint("tr_id", "target_stop_id", name="uq_risk_trip_stop"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_stop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_time_begin: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    predicted_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    predicted_delay_s: Mapped[float] = mapped_column(Float, nullable=False)
    delay_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class PredictionLogORM(Base):
    """Append-only audit trail of every prediction call (incl. safety-net
    recomputes). Never updated, only inserted — this is what you'd replay
    to check horizon compliance after the fact.
    """

    __tablename__ = "predictions_log"
    __table_args__ = (Index("ix_predlog_tr_stop", "tr_id", "target_stop_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_stop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_time_begin: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    lead_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    cur_dev_s: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_delay_s: Mapped[float] = mapped_column(Float, nullable=False)
    delay_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    is_safety_recompute: Mapped[bool] = mapped_column(Boolean, default=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
