from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session
from app.api.schemas import VehicleDeviationOut
from app.core.container import Container
from app.services.report_llm import ReportUnavailable, analyze_trip
from app.services.report_pdf import render_trip_pdf
from app.services.trip_metrics import load_trip_metrics

logger = logging.getLogger(__name__)
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


@router.post("/{vehicle_id}/report")
async def vehicle_report(vehicle_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    """Aggregates the trip, asks the model for a commentary, and returns a PDF."""
    metrics = await load_trip_metrics(session, vehicle_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail="По этому борту ещё нет телеметрии")
    try:
        analysis = await analyze_trip(metrics)
    except ReportUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("trip report model call failed for %s", vehicle_id)
        raise HTTPException(status_code=502, detail="Не удалось получить разбор модели") from exc
    pdf = render_trip_pdf(metrics, analysis)
    filename = f"report-{vehicle_id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
