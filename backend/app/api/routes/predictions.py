from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.api.schemas import RecomputeResult, RiskAssessmentOut
from app.core.container import Container
from app.core.clock import clock

router = APIRouter(tags=["predictions"])


def _to_out(assessment) -> RiskAssessmentOut:
    return RiskAssessmentOut(
        vehicle_id=assessment.vehicle_id,
        tr_id=assessment.tr_id,
        target_stop_id=assessment.target_stop_id,
        target_time_begin=assessment.target_time_begin,
        predicted_at=assessment.predicted_at,
        predicted_delay_s=assessment.predicted_delay_s,
        risk_level=assessment.risk_level.value,
        reason=assessment.reason,
        source=assessment.source.value,
        confidence=assessment.confidence,
        delay_probability=assessment.delay_probability,
    )


@router.get("/risk", response_model=list[RiskAssessmentOut])
async def list_risk(container: Container = Depends(get_container)) -> list[RiskAssessmentOut]:
    """Served straight from the in-memory StateCache - no DB round trip -
    since this is the endpoint a dashboard hits for its initial load and
    latency matters.
    """
    return [_to_out(a) for a in container.state_cache.all_risk()]


@router.get("/risk/{vehicle_id}", response_model=RiskAssessmentOut)
async def get_risk(vehicle_id: str, container: Container = Depends(get_container)) -> RiskAssessmentOut:
    assessment = container.state_cache.get_risk(vehicle_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="no risk assessment yet for this vehicle")
    return _to_out(assessment)


@router.post("/risk/recompute", response_model=RecomputeResult)
async def recompute(container: Container = Depends(get_container)) -> RecomputeResult:
    """Forces an immediate scheduler pass instead of waiting for the next
    tick - mainly useful for demos and for the jury to see the pipeline
    react on demand.
    """
    made = await container.scheduler.tick(clock.now())
    return RecomputeResult(predictions_made=made)
