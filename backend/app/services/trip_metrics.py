"""Aggregates one vehicle's stored trip into a JSON document for the report.

The PDF and the LLM both consume this document. Raw GPS is reduced to
summaries and short series so the model is not asked to re-read every fix.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PredictionLogORM, RiskAssessmentORM, ScheduleStopORM, TelemetryRecordORM
from app.services.geo import haversine_m

_MAX_POINTS = 4000
_STOP_RADIUS_M = 60.0
_STOP_WINDOW_S = 12 * 60
_STATIONARY_KMH = 2.0
_MAX_SEGMENT_KMH = 130.0


def _round(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _downsample(rows: list[dict], limit: int = 80) -> list[dict]:
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[min(int(i * step), len(rows) - 1)] for i in range(limit)]


def build_trip_metrics(
    vehicle_id: str,
    telemetry: list[TelemetryRecordORM],
    stops: list[ScheduleStopORM],
    predictions: list[PredictionLogORM],
    risks: list[RiskAssessmentORM],
) -> dict[str, Any] | None:
    if not telemetry:
        return None
    ordered = sorted(telemetry, key=lambda row: row.event_time)
    tr_id = next((row.tr_id for row in reversed(ordered) if row.tr_id is not None), None)
    valid = [row for row in ordered if row.location_valid]
    speeds = [row.speed for row in ordered]

    distance_m = 0.0
    for left, right in zip(valid, valid[1:]):
        gap_s = (right.event_time - left.event_time).total_seconds()
        if gap_s <= 0:
            continue
        segment_m = haversine_m(left.latitude, left.longitude, right.latitude, right.longitude)
        if segment_m / gap_s * 3.6 > _MAX_SEGMENT_KMH:
            continue
        distance_m += segment_m

    stopped_s = 0.0
    episodes = 0
    longest_stop_s = 0.0
    open_since: dt.datetime | None = None
    previous: TelemetryRecordORM | None = None
    for row in ordered:
        if row.speed <= _STATIONARY_KMH:
            open_since = open_since or (previous.event_time if previous else row.event_time)
        elif open_since is not None:
            span = (row.event_time - open_since).total_seconds()
            stopped_s += max(span, 0)
            longest_stop_s = max(longest_stop_s, span)
            episodes += 1
            open_since = None
        previous = row
    if open_since is not None and previous is not None:
        span = (previous.event_time - open_since).total_seconds()
        stopped_s += max(span, 0)
        longest_stop_s = max(longest_stop_s, span)
        episodes += 1

    duration_s = (ordered[-1].event_time - ordered[0].event_time).total_seconds()
    matched = _match_stops(valid, stops)
    delays = [item["delay_s"] for item in matched]
    latest_risk = max(risks, key=lambda row: row.predicted_at) if risks else None

    speed_series = _downsample([
        {"t": _iso(row.event_time), "speed_kmh": _round(row.speed)}
        for row in ordered
    ])
    return {
        "vehicle_id": vehicle_id,
        "tr_id": tr_id,
        "period": {"from": _iso(ordered[0].event_time), "to": _iso(ordered[-1].event_time), "duration_s": int(duration_s)},
        "telemetry": {
            "points": len(ordered),
            "valid_points": len(valid),
            "valid_fraction": _round(len(valid) / len(ordered), 2),
            "distance_km": _round(distance_m / 1000, 2),
            "speed_kmh": {
                "mean": _round(sum(speeds) / len(speeds)),
                "max": _round(max(speeds)),
                "p95": _round(_percentile(speeds, 0.95)),
                "median": _round(_percentile(speeds, 0.5)),
            },
            "stopped_fraction": _round(stopped_s / duration_s, 2) if duration_s > 0 else 0.0,
            "stopped_episodes": episodes,
            "longest_stop_s": int(longest_stop_s),
        },
        "schedule": {
            "stops_total": len(stops),
            "stops_passed": len(matched),
            "mean_delay_s": _round(sum(delays) / len(delays)) if delays else None,
            "max_delay_s": _round(max(delays)) if delays else None,
            "matched_stops": matched,
        },
        "predictions": [
            {
                "computed_at": _iso(row.computed_at),
                "target_stop_id": row.target_stop_id,
                "target_time_begin": _iso(row.target_time_begin),
                "lead_time_min": _round(row.lead_time_s / 60),
                "cur_dev_s": row.cur_dev_s,
                "predicted_delay_s": _round(row.predicted_delay_s),
                "delay_probability": _round(row.delay_probability, 2),
                "source": row.source,
            }
            for row in sorted(predictions, key=lambda row: row.computed_at)
        ],
        "current": None if latest_risk is None else {
            "risk_level": latest_risk.risk_level,
            "predicted_delay_s": _round(latest_risk.predicted_delay_s),
            "delay_probability": _round(latest_risk.delay_probability, 2),
            "reason": latest_risk.reason,
            "source": latest_risk.source,
            "target_stop_id": latest_risk.target_stop_id,
            "target_time_begin": _iso(latest_risk.target_time_begin),
        },
        "series": {"speed": speed_series},
    }


def _match_stops(points: list[TelemetryRecordORM], stops: list[ScheduleStopORM]) -> list[dict]:
    matched: list[dict] = []
    for stop in sorted(stops, key=lambda row: row.seq):
        if stop.latitude is None or stop.longitude is None:
            continue
        best: TelemetryRecordORM | None = None
        best_gap = _STOP_WINDOW_S
        for point in points:
            gap = abs((point.event_time - stop.scheduled_time).total_seconds())
            if gap > best_gap:
                continue
            if haversine_m(point.latitude, point.longitude, stop.latitude, stop.longitude) > _STOP_RADIUS_M:
                continue
            best = point
            best_gap = gap
        if best is None:
            continue
        delay_s = (best.event_time - stop.scheduled_time).total_seconds()
        matched.append({
            "stop_id": stop.stop_id,
            "seq": stop.seq,
            "scheduled_time": _iso(stop.scheduled_time),
            "actual_time": _iso(best.event_time),
            "delay_s": int(round(delay_s)),
        })
    return matched


async def load_trip_metrics(session: AsyncSession, vehicle_id: str) -> dict[str, Any] | None:
    telemetry = list((await session.execute(
        select(TelemetryRecordORM)
        .where(TelemetryRecordORM.vehicle_id == vehicle_id)
        .order_by(TelemetryRecordORM.event_time.desc())
        .limit(_MAX_POINTS)
    )).scalars().all())
    telemetry.reverse()
    tr_id = next((row.tr_id for row in reversed(telemetry) if row.tr_id is not None), None)
    stops = []
    if tr_id is not None:
        stops = list((await session.execute(
            select(ScheduleStopORM).where(ScheduleStopORM.tr_id == tr_id).order_by(ScheduleStopORM.seq)
        )).scalars().all())
    predictions = list((await session.execute(
        select(PredictionLogORM)
        .where(PredictionLogORM.vehicle_id == vehicle_id)
        .order_by(PredictionLogORM.computed_at.desc())
        .limit(30)
    )).scalars().all())
    risks = list((await session.execute(
        select(RiskAssessmentORM).where(RiskAssessmentORM.vehicle_id == vehicle_id)
    )).scalars().all())
    return build_trip_metrics(vehicle_id, telemetry, stops, predictions, risks)
