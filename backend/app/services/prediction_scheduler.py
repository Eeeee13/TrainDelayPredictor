"""Schedule first and high-risk repeat predictions strictly in (T+10, T+15] minutes."""
from __future__ import annotations

import datetime as dt
import logging
import time

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bus.event_bus import TOPIC_ALERTS, TOPIC_PREDICTIONS, EventBus
from app.core.config import settings
from app.core.clock import clock
from app.db.models import PredictionLogORM
from app.domain.entities import RiskLevel, ScheduleStop, VehicleState
from app.repositories.prediction_repo import PredictionRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.services.feature_builder import FeatureBuilder
from app.services.inference_client import InferenceClient
from app.services.matching_engine import MatchingEngine
from app.services.risk_aggregator import RiskAggregator
from app.services.state_cache import StateCache
from app.services.websocket_hub import WebSocketHub

logger = logging.getLogger(__name__)


class _Candidate:
    __slots__ = ("state", "target", "is_safety_recompute")

    def __init__(self, state: VehicleState, target: ScheduleStop, is_safety_recompute: bool) -> None:
        self.state = state
        self.target = target
        self.is_safety_recompute = is_safety_recompute


class PredictionScheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        state_cache: StateCache,
        matching_engine: MatchingEngine,
        feature_builder: FeatureBuilder,
        inference_client: InferenceClient,
        risk_aggregator: RiskAggregator,
        event_bus: EventBus,
        ws_hub: WebSocketHub,
    ) -> None:
        self._session_factory = session_factory
        self._state = state_cache
        self._matching = matching_engine
        self._features = feature_builder
        self._inference = inference_client
        self._risk = risk_aggregator
        self._bus = event_bus
        self._ws = ws_hub
        self._last_safety_pass: dt.datetime | None = None
        self._running = False

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.tick(clock.now())
            except Exception:  # noqa: BLE001 - the tick loop must never die
                logger.exception("prediction scheduler tick failed")
            await self._sleep(max(0.05, clock.real_seconds(settings.scheduler_tick_s)))

    async def _sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def stop(self) -> None:
        self._running = False

    async def tick(self, now: dt.datetime) -> int:
        """Runs one scheduling pass. Returns the number of predictions made
        (exposed so `/risk/recompute` and tests can assert on it).
        """
        due_safety_pass = (
            self._last_safety_pass is None
            or (now - self._last_safety_pass).total_seconds() >= settings.safety_recompute_interval_s
        )

        async with self._session_factory() as session:
            schedule_repo = ScheduleRepository(session)
            upcoming = await schedule_repo.upcoming_stops(now, settings.schedule_lookahead_s)
        trip_stops: dict[int, list[ScheduleStop]] = {}
        for stop in upcoming:
            trip_stops.setdefault(stop.tr_id, []).append(stop)
        for stops in trip_stops.values():
            stops.sort(key=lambda s: s.seq)

        candidates = self._collect_candidates(now, trip_stops, due_safety_pass)
        if not candidates:
            if due_safety_pass:
                self._last_safety_pass = now
            return 0

        items = [self._features.build(c.state, c.target, now) for c in candidates]
        inference_started = time.perf_counter()
        results = await self._inference.predict_batch(items)
        logger.info(
            "inference_batch items=%d vehicles=%d elapsed_ms=%.3f model=%d fallback=%d",
            len(items), len({item.tr_id for item in items}),
            (time.perf_counter() - inference_started) * 1000,
            sum(result.source.value == "model" for result in results),
            sum(result.source.value == "fallback" for result in results),
        )
        results_by_id = {r.request_id: r for r in results}

        async with self._session_factory() as session:
            pred_repo = PredictionRepository(session)
            made = 0
            for candidate, item in zip(candidates, items):
                result = results_by_id.get(item.request_id)
                if result is None:
                    continue
                assessment = self._risk.assess(candidate.state, item, result, now)
                self._state.put_risk(assessment)
                if not candidate.is_safety_recompute:
                    self._state.mark_predicted(item.tr_id, item.target_stop_id)

                await pred_repo.upsert_risk(assessment)
                lead_time_s = (item.target_time_begin - item.T).total_seconds()
                await pred_repo.append_log(
                    PredictionLogORM(
                        vehicle_id=candidate.state.vehicle_id,
                        tr_id=item.tr_id,
                        target_stop_id=item.target_stop_id,
                        target_time_begin=item.target_time_begin,
                        computed_at=now,
                        lead_time_s=lead_time_s,
                        cur_dev_s=item.cur_dev_s,
                        predicted_delay_s=result.predicted_delay_s,
                        source=result.source.value,
                        is_safety_recompute=candidate.is_safety_recompute,
                        model_version=result.model_version,
                        delay_probability=result.delay_probability,
                    )
                )

                await self._bus.publish(TOPIC_PREDICTIONS, assessment.to_dict())
                if assessment.risk_level == RiskLevel.HIGH:
                    await self._bus.publish(TOPIC_ALERTS, assessment.to_dict())
                await self._ws.broadcast(assessment)
                made += 1

        if due_safety_pass:
            self._last_safety_pass = now
        return made

    def _collect_candidates(
        self,
        now: dt.datetime,
        trip_stops: dict[int, list[ScheduleStop]],
        due_safety_pass: bool,
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for state in self._state.active_vehicles(now, settings.stale_vehicle_after_s):
            if state.tr_id is None:
                continue
            stops = trip_stops.get(state.tr_id)
            if not stops:
                continue
            in_window = sorted(
                (s for s in stops if settings.horizon_min_s < (s.scheduled_time - now).total_seconds()
                 <= settings.horizon_max_s),
                key=lambda s: (s.scheduled_time, s.seq),
            )
            if in_window:
                target = in_window[0]
                pair_done = self._state.already_predicted(state.tr_id, target.stop_id)
                if not pair_done:
                    candidates.append(_Candidate(state, target, is_safety_recompute=False))
                elif due_safety_pass:
                    risk = self._state.get_risk(state.vehicle_id)
                    if risk is not None and risk.risk_level == RiskLevel.HIGH and risk.target_stop_id == target.stop_id:
                        candidates.append(_Candidate(state, target, is_safety_recompute=True))
                continue

        return candidates
