"""Composition root: the one place that wires concrete implementations
together. Routes and workers receive collaborators from here (via
`app.state.container` + FastAPI `Depends`), never construct them
themselves - that's the whole point of keeping DI in one spot instead of
scattered `new X()` calls.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select

from app.bus.event_bus import EventBus, build_event_bus
from app.core.config import settings
from app.db.session import get_session_factory
from app.db.models import TelemetryRecordORM, PredictionLogORM
from app.domain.entities import TelemetryRecord
from app.repositories.schedule_repo import ScheduleRepository
from app.services.feature_builder import FeatureBuilder
from app.services.inference_client import InferenceClient, build_inference_client
from app.services.matching_engine import MatchingEngine
from app.services.prediction_scheduler import PredictionScheduler
from app.services.risk_aggregator import RiskAggregator
from app.services.state_cache import StateCache
from app.services.websocket_hub import WebSocketHub
from app.workers.telemetry_worker import TelemetryWorker


@dataclass
class Container:
    session_factory: async_sessionmaker
    event_bus: EventBus
    state_cache: StateCache
    matching_engine: MatchingEngine
    feature_builder: FeatureBuilder
    inference_client: InferenceClient
    risk_aggregator: RiskAggregator
    ws_hub: WebSocketHub
    telemetry_worker: TelemetryWorker
    scheduler: PredictionScheduler


async def build_container() -> Container:
    session_factory = get_session_factory()
    event_bus = await build_event_bus(settings.redis_url, settings.use_redis_streams)

    state_cache = StateCache()
    matching_engine = MatchingEngine()
    feature_builder = FeatureBuilder()
    inference_client = build_inference_client()
    risk_aggregator = RiskAggregator()
    ws_hub = WebSocketHub()

    # Rebuild rolling state and the one-time alert guard after a restart.
    async with session_factory() as session:
        rows = (await session.execute(select(TelemetryRecordORM).order_by(TelemetryRecordORM.event_time))).scalars().all()
        schedule_repo = ScheduleRepository(session)
        stops_cache = {}
        for row in rows:
            if row.tr_id is not None and row.tr_id not in stops_cache:
                stops_cache[row.tr_id] = await schedule_repo.stops_for_trip(row.tr_id)
            record = TelemetryRecord(vehicle_id=row.vehicle_id, tr_id=row.tr_id,
                                     event_time=row.event_time, latitude=row.latitude,
                                     longitude=row.longitude, speed=row.speed,
                                     door_open=row.door_open, location_valid=row.location_valid)
            previous = state_cache.get_vehicle(row.vehicle_id)
            state_cache.put_vehicle(matching_engine.update(previous, record, stops_cache.get(row.tr_id, [])))
        logs = (await session.execute(select(PredictionLogORM.tr_id, PredictionLogORM.target_stop_id)
                                      .where(PredictionLogORM.is_safety_recompute == False))).all()
        for tr_id, stop_id in logs:
            state_cache.mark_predicted(tr_id, stop_id)

    telemetry_worker = TelemetryWorker(session_factory, event_bus, state_cache, matching_engine)
    scheduler = PredictionScheduler(
        session_factory=session_factory,
        state_cache=state_cache,
        matching_engine=matching_engine,
        feature_builder=feature_builder,
        inference_client=inference_client,
        risk_aggregator=risk_aggregator,
        event_bus=event_bus,
        ws_hub=ws_hub,
    )

    return Container(
        session_factory=session_factory,
        event_bus=event_bus,
        state_cache=state_cache,
        matching_engine=matching_engine,
        feature_builder=feature_builder,
        inference_client=inference_client,
        risk_aggregator=risk_aggregator,
        ws_hub=ws_hub,
        telemetry_worker=telemetry_worker,
        scheduler=scheduler,
    )
