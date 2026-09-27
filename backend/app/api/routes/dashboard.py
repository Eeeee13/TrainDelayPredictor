"""Compact read-only map snapshot for the dispatcher UI."""
from __future__ import annotations

import datetime as dt
import math

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import get_container
from app.core.container import Container
from app.core.clock import clock
from app.db.models import RiskAssessmentORM, ScheduleStopORM, TelemetryRecordORM

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _current_trail(points: list[TelemetryRecordORM]) -> list[TelemetryRecordORM]:
    """Keep only the continuous GPS segment ending at the latest fix."""
    if not points:
        return []
    segment = [points[0]]
    for point in points[1:]:
        newer = segment[-1]
        lat_m = (newer.latitude - point.latitude) * 111_200
        lon_m = (newer.longitude - point.longitude) * 111_200 * math.cos(math.radians(newer.latitude))
        if math.hypot(lat_m, lon_m) > 2_000 or newer.event_time - point.event_time > dt.timedelta(minutes=5):
            break
        segment.append(point)
    return list(reversed(segment))


@router.get("/snapshot")
async def snapshot(container: Container = Depends(get_container)) -> dict:
    snapshot_time = clock.now()
    ranked = select(
        TelemetryRecordORM.id.label("id"),
        func.row_number().over(
            partition_by=TelemetryRecordORM.vehicle_id,
            order_by=(TelemetryRecordORM.event_time.desc(), TelemetryRecordORM.id.desc()),
        ).label("rank"),
    ).where(
        TelemetryRecordORM.event_time <= snapshot_time,
        TelemetryRecordORM.event_time >= snapshot_time - dt.timedelta(minutes=10),
    )
    if hasattr(TelemetryRecordORM, "location_valid"):
        ranked = ranked.where(TelemetryRecordORM.location_valid.is_(True))
    ranked = ranked.subquery()

    async with container.session_factory() as session:
        telemetry = (await session.scalars(
            select(TelemetryRecordORM)
            .join(ranked, TelemetryRecordORM.id == ranked.c.id)
            .where(ranked.c.rank == 1, TelemetryRecordORM.tr_id.is_not(None))
            .order_by(TelemetryRecordORM.event_time.desc())
            .limit(200)
        )).all()
        stored_risks = (await session.scalars(select(RiskAssessmentORM))).all()
        risk_by_vehicle = {risk.vehicle_id: risk for risk in stored_risks}
        risk_by_vehicle.update({risk.vehicle_id: risk for risk in container.state_cache.all_risk()})

        vehicles = []
        routes = []
        for point in telemetry:
            risk = risk_by_vehicle.get(point.vehicle_id)
            if risk is not None and (risk.tr_id != point.tr_id or abs((point.event_time - risk.predicted_at).total_seconds()) > 1800):
                risk = None
            state = container.state_cache.get_vehicle(point.vehicle_id)
            trail_query = (
                select(TelemetryRecordORM)
                .where(
                    TelemetryRecordORM.vehicle_id == point.vehicle_id,
                    TelemetryRecordORM.event_time <= point.event_time,
                    TelemetryRecordORM.event_time >= point.event_time - dt.timedelta(minutes=30),
                )
                .order_by(TelemetryRecordORM.event_time.desc())
                .limit(120)
            )
            if hasattr(TelemetryRecordORM, "location_valid"):
                trail_query = trail_query.where(TelemetryRecordORM.location_valid.is_(True))
            recent_points = (await session.scalars(trail_query)).all()
            current_trail = _current_trail(recent_points)
            vehicles.append({
                "vehicle_id": point.vehicle_id,
                "tr_id": point.tr_id,
                "position": {"lat": point.latitude, "lng": point.longitude},
                "speed_kmh": point.speed,
                "event_time": point.event_time.isoformat(),
                "cur_dev_s": state.cur_dev_s if state is not None else None,
                "trail": [
                    {"lat": fix.latitude, "lng": fix.longitude}
                    for fix in current_trail
                ],
                "risk": risk.to_dict() if hasattr(risk, "to_dict") else (
                    {"vehicle_id": risk.vehicle_id, "tr_id": risk.tr_id,
                     "target_stop_id": risk.target_stop_id,
                     "target_time_begin": risk.target_time_begin.isoformat(),
                     "predicted_at": risk.predicted_at.isoformat(),
                     "predicted_delay_s": risk.predicted_delay_s,
                     "risk_level": risk.risk_level, "source": risk.source,
                     "delay_probability": risk.delay_probability}
                    if risk is not None else None
                ),
            })

            stops = (await session.scalars(
                select(ScheduleStopORM)
                .where(ScheduleStopORM.tr_id == point.tr_id,
                       ScheduleStopORM.latitude.is_not(None),
                       ScheduleStopORM.longitude.is_not(None))
                .order_by(ScheduleStopORM.scheduled_time, ScheduleStopORM.seq)
            )).all()
            if not stops:
                continue
            target_id = risk.target_stop_id if risk is not None else None
            center = next((i for i, stop in enumerate(stops) if stop.stop_id == target_id), None)
            if center is None:
                center = min(range(len(stops)), key=lambda i: abs((stops[i].scheduled_time - point.event_time).total_seconds()))
            if risk is None and abs((stops[center].scheduled_time - point.event_time).total_seconds()) > 7200:
                continue
            window = stops[max(0, center - 8):center + 9]
            routes.append({
                "id": str(point.tr_id),
                "vehicle_id": point.vehicle_id,
                "short_name": window[0].route_id or str(point.tr_id),
                "stops": [
                    {"id": str(stop.stop_id), "sequence": stop.seq,
                     "address": stop.address,
                     "scheduled_time": stop.scheduled_time.isoformat(),
                     "position": {"lat": stop.latitude, "lng": stop.longitude}}
                    for stop in window
                ],
            })

    return {"vehicles": vehicles, "routes": routes}
