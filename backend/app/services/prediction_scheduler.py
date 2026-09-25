"""PredictionScheduler: decides *when* to call the ML model.

This is the answer to "not by timer, not on arrival, but by a calendar of
forecast moments derived from the schedule":

  * Every stop still ahead of a vehicle has a known `target_time_begin`
    from the reference schedule.
  * The moment `target_time_begin - now` first falls inside
    [horizon_min_s, horizon_max_s] (15..10 minutes out), that (tr_id,
    target_stop_id) pair becomes *due* and gets exactly one "first"
    prediction — this is the early warning, fired as early as the window
    allows.
  * A safety-net recompute runs every ~60s, but only refreshes pairs that
    already got their first prediction and are currently HIGH risk, and
    only while the event is still in the future. It never creates a new
    "first" alert and never fires after the event would already have
    happened (no forecasts issued after the fact).
  * A telemetry gap can make a vehicle miss the ideal window; if so we
    still fire once, as long as the event genuinely hasn't happened yet
    (>= late_fire_floor_s away), rather than silently giving up.

Idempotency is enforced in-memory (StateCache._predicted_pairs) since this
scheduler is the sole writer running on a single asyncio task — no
distributed locking needed at this scale.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bus.event_bus import TOPIC_ALERTS, TOPIC_PREDICTIONS, EventBus
from app.core.config import settings
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
        self._last_safety_pass = dt.datetime.min
        self._running = False

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.tick(dt.datetime.utcnow())
            except Exception:  # noqa: BLE001 - the tick loop must never die
                logger.exception("prediction scheduler tick failed")
            await self._sleep(settings.scheduler_tick_s)

    async def _sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def stop(self) -> None:
        self._running = False

    async def tick(self, now: dt.datetime) -> int:
        """Runs one scheduling pass. Returns the number of predictions made
        (exposed so `/risk/recompute` and tests can assert on it).
        """
        due_safety_pass = (now - self._last_safety_pass).total_seconds() >= settings.safety_recompute_interval_s

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
            results = await self._inference.predict_batch(items)
            results_by_id = {r.request_id: r for r in results}

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
            target = self._matching.next_target(state, stops)
            if target is None:
                continue

            remaining_s = (target.scheduled_time - now).total_seconds()
            if remaining_s <= 0:
                # event already happened - never issue a "prediction" for
                # the past (anti-leakage / no after-the-fact alerts).
                continue

            pair_done = self._state.already_predicted(state.tr_id, target.stop_id)

            if not pair_done:
                in_window = settings.horizon_min_s <= remaining_s <= settings.horizon_max_s
                missed_but_salvageable = remaining_s < settings.horizon_min_s and remaining_s >= settings.late_fire_floor_s
                if in_window or missed_but_salvageable:
                    candidates.append(_Candidate(state, target, is_safety_recompute=False))
                continue

            if due_safety_pass:
                risk = self._state.get_risk(state.vehicle_id)
                if risk is not None and risk.risk_level == RiskLevel.HIGH and risk.target_stop_id == target.stop_id:
                    candidates.append(_Candidate(state, target, is_safety_recompute=True))
        return candidates
