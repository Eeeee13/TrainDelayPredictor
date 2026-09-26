from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScheduleStopORM
from app.domain.entities import ScheduleStop


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_upsert(self, stops: list[ScheduleStop], route_id: str | None = None, vehicle_id: str | None = None) -> int:
        if not stops:
            return 0
        rows = [
            dict(
                tr_id=s.tr_id,
                stop_id=s.stop_id,
                seq=s.seq,
                scheduled_time=s.scheduled_time,
                latitude=s.latitude,
                longitude=s.longitude,
                route_id=route_id,
                vehicle_id=vehicle_id,
                manual_fill=s.manual_fill,
            )
            for s in stops
        ]
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = pg_insert(ScheduleStopORM).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["tr_id", "stop_id"],
                set_=dict(
                    seq=stmt.excluded.seq,
                    scheduled_time=stmt.excluded.scheduled_time,
                    latitude=stmt.excluded.latitude,
                    longitude=stmt.excluded.longitude,
                    manual_fill=stmt.excluded.manual_fill,
                ),
            )
            await self._session.execute(stmt)
        else:
            for row in rows:
                existing = await self._session.execute(
                    select(ScheduleStopORM).where(
                        ScheduleStopORM.tr_id == row["tr_id"], ScheduleStopORM.stop_id == row["stop_id"]
                    )
                )
                obj = existing.scalar_one_or_none()
                if obj is None:
                    self._session.add(ScheduleStopORM(**row))
                else:
                    for k, v in row.items():
                        setattr(obj, k, v)
        await self._session.commit()
        return len(rows)

    async def upcoming_stops(self, now: dt.datetime, lookahead_s: int) -> list[ScheduleStop]:
        """Every scheduled stop between now and now+lookahead — the raw
        material the PredictionScheduler turns into a due-prediction
        calendar.
        """
        horizon = now + dt.timedelta(seconds=lookahead_s)
        result = await self._session.execute(
            select(ScheduleStopORM).where(
                ScheduleStopORM.scheduled_time >= now, ScheduleStopORM.scheduled_time <= horizon
            )
        )
        return [
            ScheduleStop(
                tr_id=row.tr_id,
                stop_id=row.stop_id,
                seq=row.seq,
                scheduled_time=row.scheduled_time,
                latitude=row.latitude,
                longitude=row.longitude,
                manual_fill=row.manual_fill,
            )
            for row in result.scalars().all()
        ]

    async def stops_for_trip(self, tr_id: int) -> list[ScheduleStop]:
        result = await self._session.execute(
            select(ScheduleStopORM).where(ScheduleStopORM.tr_id == tr_id).order_by(ScheduleStopORM.seq)
        )
        return [
            ScheduleStop(
                tr_id=row.tr_id,
                stop_id=row.stop_id,
                seq=row.seq,
                scheduled_time=row.scheduled_time,
                latitude=row.latitude,
                longitude=row.longitude,
                manual_fill=row.manual_fill,
            )
            for row in result.scalars().all()
        ]
