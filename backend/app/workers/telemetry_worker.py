"""Consumes normalized telemetry off the `telemetry` topic, persists it,
runs the MatchingEngine, and updates the in-memory StateCache.

This is the seam that decouples "accepting an NDTP packet" (must ack fast)
from "computing derived features" (can take a few ms) - exactly the
telemetry -> features hop in the topic layout.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bus.event_bus import TOPIC_FEATURES, TOPIC_TELEMETRY, EventBus
from app.domain.entities import TelemetryRecord
from app.repositories.schedule_repo import ScheduleRepository
from app.repositories.telemetry_repo import TelemetryRepository
from app.services.matching_engine import MatchingEngine
from app.services.state_cache import StateCache

logger = logging.getLogger(__name__)


class TelemetryWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        event_bus: EventBus,
        state_cache: StateCache,
        matching_engine: MatchingEngine,
    ) -> None:
        self._session_factory = session_factory
        self._bus = event_bus
        self._state = state_cache
        self._matching = matching_engine
        self._trip_stops_cache: dict[int, tuple[dt.datetime, list]] = {}
        self._trip_stops_ttl_s = 30

    async def run_forever(self) -> None:
        async for payload in self._bus.subscribe(TOPIC_TELEMETRY):
            try:
                await self._handle(payload)
            except Exception:  # noqa: BLE001 - one bad packet must not kill the consumer loop
                logger.exception("failed to process telemetry payload: %s", payload)

    async def _handle(self, payload: dict) -> None:
        record = TelemetryRecord(
            vehicle_id=payload["vehicle_id"],
            event_time=dt.datetime.fromisoformat(payload["event_time"]),
            latitude=payload["latitude"],
            longitude=payload["longitude"],
            speed=payload.get("speed", 0.0),
            door_open=payload.get("door_open", False),
            tr_id=payload.get("tr_id"),
        )

        async with self._session_factory() as session:
            await TelemetryRepository(session).bulk_upsert([record])
            trip_stops = await self._get_trip_stops(session, record.tr_id) if record.tr_id else []

        prev = self._state.get_vehicle(record.vehicle_id)
        new_state = self._matching.update(prev, record, trip_stops)
        self._state.put_vehicle(new_state)

        await self._bus.publish(
            TOPIC_FEATURES,
            {
                "vehicle_id": new_state.vehicle_id,
                "tr_id": new_state.tr_id,
                "cur_dev_s": new_state.cur_dev_s,
                "avg_speed_segment": new_state.avg_speed_segment,
                "updated_at": new_state.updated_at.isoformat() if new_state.updated_at else None,
            },
        )

    async def _get_trip_stops(self, session, tr_id: int) -> list:
        cached = self._trip_stops_cache.get(tr_id)
        now = dt.datetime.utcnow()
        if cached is not None and (now - cached[0]).total_seconds() < self._trip_stops_ttl_s:
            return cached[1]
        stops = await ScheduleRepository(session).stops_for_trip(tr_id)
        self._trip_stops_cache[tr_id] = (now, stops)
        return stops
