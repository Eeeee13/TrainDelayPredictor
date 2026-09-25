from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.api.schemas import VehicleDeviationOut
from app.core.container import Container

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/{vehicle_id}/deviation", response_model=VehicleDeviationOut)
async def get_deviation(vehicle_id: str, container: Container = Depends(get_container)) -> VehicleDeviationOut:
    """The raw, non-ML deviation signal (Matching Engine output) - also the
    exact fallback value the model degrades to when unavailable.
    """
    state = container.state_cache.get_vehicle(vehicle_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown or silent vehicle")
    return VehicleDeviationOut(
        vehicle_id=state.vehicle_id,
        tr_id=state.tr_id,
        cur_dev_s=state.cur_dev_s,
        last_matched_stop_id=state.last_matched_stop_id,
        avg_speed_segment=state.avg_speed_segment,
        last_event_time=state.last_event_time,
        is_stationary=state.stationary_since is not None,
    )
