"""Ingestion endpoints. Telemetry is fire-and-forget onto the `telemetry`
topic — the handler only validates and enqueues, so accepting an NDTP
packet stays sub-millisecond regardless of how busy the matching/feature
pipeline is (backpressure lives in the queue, not in the HTTP response).

Schedule updates are comparatively rare/bulky, so they're persisted
synchronously - a dispatcher waiting on "did my timetable upload work"
wants a real answer, not a 202.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session
from app.api.schemas import IngestAck, ScheduleBatchIn, TelemetryBatchIn
from app.bus.event_bus import TOPIC_TELEMETRY
from app.core.container import Container
from app.domain.entities import ScheduleStop
from app.repositories.schedule_repo import ScheduleRepository

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/telemetry", response_model=IngestAck, status_code=202)
async def ingest_telemetry(batch: TelemetryBatchIn, container: Container = Depends(get_container)) -> IngestAck:
    for record in batch.records:
        await container.event_bus.publish(
            TOPIC_TELEMETRY,
            {
                "vehicle_id": record.vehicle_id,
                "event_time": record.event_time.isoformat(),
                "latitude": record.latitude,
                "longitude": record.longitude,
                "speed": record.speed,
                "door_open": record.door_open,
                "tr_id": record.tr_id,
            },
        )
    return IngestAck(accepted=len(batch.records))


@router.post("/schedule", response_model=IngestAck)
async def ingest_schedule(batch: ScheduleBatchIn, session: AsyncSession = Depends(get_session)) -> IngestAck:
    stops = [
        ScheduleStop(
            tr_id=s.tr_id,
            stop_id=s.stop_id,
            seq=s.seq,
            scheduled_time=s.scheduled_time,
            latitude=s.latitude,
            longitude=s.longitude,
        )
        for s in batch.stops
    ]
    count = await ScheduleRepository(session).bulk_upsert(stops, route_id=batch.route_id, vehicle_id=batch.vehicle_id)
    return IngestAck(accepted=count)
