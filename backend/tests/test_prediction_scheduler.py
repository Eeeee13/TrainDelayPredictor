import datetime as dt

import pytest

from app.bus.event_bus import MemoryEventBus
from app.domain.entities import RiskLevel, ScheduleStop, VehicleState
from app.repositories.schedule_repo import ScheduleRepository
from app.services.feature_builder import FeatureBuilder
from app.services.inference_client import HeuristicFallbackInferenceClient
from app.services.matching_engine import MatchingEngine
from app.services.prediction_scheduler import PredictionScheduler
from app.services.risk_aggregator import RiskAggregator
from app.services.state_cache import StateCache
from app.services.websocket_hub import WebSocketHub


async def _make_scheduler(session_factory, medium=120, high=300):
    return PredictionScheduler(
        session_factory=session_factory,
        state_cache=StateCache(),
        matching_engine=MatchingEngine(),
        feature_builder=FeatureBuilder(),
        inference_client=HeuristicFallbackInferenceClient(),
        risk_aggregator=RiskAggregator(medium_threshold_s=medium, high_threshold_s=high),
        event_bus=MemoryEventBus(),
        ws_hub=WebSocketHub(),
    )


async def _seed_stop(session_factory, tr_id, stop_id, seq, scheduled_time):
    async with session_factory() as session:
        await ScheduleRepository(session).bulk_upsert(
            [ScheduleStop(tr_id=tr_id, stop_id=stop_id, seq=seq, scheduled_time=scheduled_time)]
        )


async def test_fires_once_inside_horizon_window(sqlite_session_factory):
    now = dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory, tr_id=1, stop_id=101, seq=1, scheduled_time=now + dt.timedelta(minutes=12))

    scheduler = await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=310, last_event_time=now, last_matched_seq=0))

    made = await scheduler.tick(now)
    assert made == 1
    assert scheduler._state.already_predicted(1, 101)
    assert scheduler._state.get_risk("bus-1").risk_level == RiskLevel.HIGH


async def test_does_not_fire_outside_horizon_window(sqlite_session_factory):
    now = dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory, tr_id=1, stop_id=101, seq=1, scheduled_time=now + dt.timedelta(minutes=30))

    scheduler = await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=310, last_event_time=now, last_matched_seq=0))

    made = await scheduler.tick(now)
    assert made == 0


async def test_never_fires_for_a_stop_already_in_the_past(sqlite_session_factory):
    now = dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory, tr_id=1, stop_id=101, seq=1, scheduled_time=now - dt.timedelta(minutes=1))

    scheduler = await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=310, last_event_time=now, last_matched_seq=0))

    made = await scheduler.tick(now)
    assert made == 0  # anti-leak: never predict something that already happened


async def test_is_idempotent_without_safety_pass(sqlite_session_factory):
    now = dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory, tr_id=1, stop_id=101, seq=1, scheduled_time=now + dt.timedelta(minutes=12))

    scheduler = await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=50, last_event_time=now, last_matched_seq=0))
    scheduler._last_safety_pass = now  # suppress safety pass for this call

    first = await scheduler.tick(now)
    second = await scheduler.tick(now)
    assert first == 1
    assert second == 0  # low risk + already predicted + no safety pass due -> nothing to do


async def test_safety_recompute_refreshes_high_risk_pair(sqlite_session_factory):
    now = dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory, tr_id=1, stop_id=101, seq=1, scheduled_time=now + dt.timedelta(minutes=12))

    scheduler = await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=310, last_event_time=now, last_matched_seq=0))
    scheduler._last_safety_pass = now - dt.timedelta(seconds=61)  # force safety pass due

    first = await scheduler.tick(now)
    assert first == 1
    # first tick already reset _last_safety_pass; force it due again
    scheduler._last_safety_pass = now - dt.timedelta(seconds=61)
    second = await scheduler.tick(now + dt.timedelta(seconds=2))
    assert second == 1  # high-risk pair gets refreshed by the safety net


async def test_selects_first_stop_in_strict_horizon(sqlite_session_factory):
    now = dt.datetime.utcnow()
    async with sqlite_session_factory() as session:
        await ScheduleRepository(session).bulk_upsert([
            ScheduleStop(tr_id=1, stop_id=101, seq=1, scheduled_time=now + dt.timedelta(minutes=2)),
            ScheduleStop(tr_id=1, stop_id=102, seq=2, scheduled_time=now + dt.timedelta(minutes=12)),
            ScheduleStop(tr_id=1, stop_id=103, seq=3, scheduled_time=now + dt.timedelta(minutes=14)),
        ])
    scheduler = await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=100, last_event_time=now))
    assert await scheduler.tick(now) == 1
    assert scheduler._state.get_risk("bus-1").target_stop_id == 102


@pytest.mark.parametrize('lead,expected', [(30,0),(599,0),(600,0),(601,1),(900,1),(901,0)])
async def test_strict_boundaries_even_with_fallback(sqlite_session_factory, lead, expected):
    now = dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory,1,101,1,now+dt.timedelta(seconds=lead))
    scheduler=await _make_scheduler(sqlite_session_factory)
    scheduler._state.put_vehicle(VehicleState(vehicle_id='bus-1',tr_id=1,cur_dev_s=310,last_event_time=now))
    assert await scheduler.tick(now)==expected
    if expected:
        assert scheduler._state.get_risk('bus-1').delay_probability is None


async def test_high_risk_does_not_recompute_after_window(sqlite_session_factory):
    now=dt.datetime.utcnow()
    await _seed_stop(sqlite_session_factory,1,101,1,now+dt.timedelta(seconds=660))
    scheduler=await _make_scheduler(sqlite_session_factory)
    state=VehicleState(vehicle_id='bus-1',tr_id=1,cur_dev_s=310,last_event_time=now)
    scheduler._state.put_vehicle(state)
    assert await scheduler.tick(now)==1
    assert await scheduler.tick(now+dt.timedelta(seconds=60))==0
