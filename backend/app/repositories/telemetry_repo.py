from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TelemetryRecordORM
from app.domain.entities import TelemetryRecord


class TelemetryRepository:
    """Persists normalized telemetry for durability/audit. Ingestion is
    idempotent on (vehicle_id, event_time): replaying the same NDTP packet
    twice (e.g. after a reconnect) never double-counts.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_upsert(self, records: list[TelemetryRecord]) -> int:
        if not records:
            return 0
        rows = [
            dict(
                vehicle_id=r.vehicle_id,
                event_time=r.event_time,
                latitude=r.latitude,
                longitude=r.longitude,
                speed=r.speed,
                door_open=r.door_open,
                tr_id=r.tr_id,
                location_valid=r.location_valid,
            )
            for r in records
        ]
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = pg_insert(TelemetryRecordORM).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["vehicle_id", "event_time"])
            await self._session.execute(stmt)
        else:
            # portable fallback for sqlite (tests): skip rows that already exist
            for row in rows:
                exists = await self._session.execute(
                    select(TelemetryRecordORM.id).where(
                        TelemetryRecordORM.vehicle_id == row["vehicle_id"],
                        TelemetryRecordORM.event_time == row["event_time"],
                    )
                )
                if exists.scalar_one_or_none() is None:
                    self._session.add(TelemetryRecordORM(**row))
        await self._session.commit()
        return len(rows)
