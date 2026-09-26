from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PredictionLogORM, RiskAssessmentORM
from app.domain.entities import RiskAssessment


class PredictionRepository:
    """Owns two tables: `risk_assessments` (latest state, upserted — what
    the dashboard's initial REST load reads) and `predictions_log`
    (append-only audit trail, one row per model call including safety-net
    recomputes).

    Writes come from the single-writer PredictionScheduler task, so plain
    select-then-write upserts are safe here without extra locking.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_risk(self, assessment: RiskAssessment) -> None:
        result = await self._session.execute(
            select(RiskAssessmentORM).where(
                RiskAssessmentORM.tr_id == assessment.tr_id,
                RiskAssessmentORM.target_stop_id == assessment.target_stop_id,
            )
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            obj = RiskAssessmentORM(tr_id=assessment.tr_id, target_stop_id=assessment.target_stop_id)
            self._session.add(obj)
        obj.vehicle_id = assessment.vehicle_id
        obj.target_time_begin = assessment.target_time_begin
        obj.predicted_at = assessment.predicted_at
        obj.predicted_delay_s = assessment.predicted_delay_s
        obj.risk_level = assessment.risk_level.value
        obj.reason = assessment.reason
        obj.source = assessment.source.value
        obj.confidence = assessment.confidence
        await self._session.commit()

    async def append_log(self, log: PredictionLogORM) -> None:
        self._session.add(log)
        await self._session.commit()

    async def latest_risk(self, vehicle_id: str | None = None) -> list[RiskAssessmentORM]:
        stmt = select(RiskAssessmentORM)
        if vehicle_id:
            stmt = stmt.where(RiskAssessmentORM.vehicle_id == vehicle_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
