import datetime as dt
from types import SimpleNamespace

import pytest

from app.api.routes.dashboard import _current_trail, snapshot
from app.core.clock import clock
from app.db.models import RiskAssessmentORM, ScheduleStopORM, TelemetryRecordORM


class EmptyCache:
    def all_risk(self):
        return []

    def get_vehicle(self, _vehicle_id):
        return None


def test_current_trail_stops_at_emulator_reset_jump():
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    points = [
        SimpleNamespace(latitude=55.75, longitude=37.61, event_time=now),
        SimpleNamespace(latitude=55.749, longitude=37.609, event_time=now-dt.timedelta(seconds=2)),
        SimpleNamespace(latitude=55.70, longitude=37.50, event_time=now-dt.timedelta(seconds=4)),
    ]
    assert _current_trail(points) == [points[1], points[0]]


@pytest.mark.asyncio
async def test_dashboard_uses_valid_position_and_fresh_prediction(sqlite_session_factory):
    clock.resume_live()
    now = dt.datetime.utcnow().replace(microsecond=0)
    async with sqlite_session_factory() as session:
        session.add_all([
            TelemetryRecordORM(vehicle_id="bus-1", tr_id=7, event_time=now-dt.timedelta(minutes=4), latitude=55.75, longitude=37.61, speed=22, location_valid=True),
            TelemetryRecordORM(vehicle_id="bus-1", tr_id=7, event_time=now-dt.timedelta(minutes=5), latitude=55.74, longitude=37.60, speed=20, location_valid=True),
            TelemetryRecordORM(vehicle_id="bus-1", tr_id=7, event_time=now-dt.timedelta(minutes=3), latitude=1, longitude=1, speed=0, location_valid=False),
            ScheduleStopORM(tr_id=7, stop_id=11, seq=1, scheduled_time=now-dt.timedelta(minutes=3), latitude=55.75, longitude=37.61),
            ScheduleStopORM(tr_id=7, stop_id=12, seq=2, scheduled_time=now+dt.timedelta(minutes=10), latitude=55.76, longitude=37.62),
            RiskAssessmentORM(vehicle_id="bus-1", tr_id=7, target_stop_id=12, target_time_begin=now+dt.timedelta(minutes=10), predicted_at=now-dt.timedelta(minutes=5), predicted_delay_s=350, risk_level="high", reason="delay", source="model"),
        ])
        await session.commit()
    container = SimpleNamespace(session_factory=sqlite_session_factory, state_cache=EmptyCache())
    result = await snapshot(container)
    assert len(result["vehicles"]) == 1
    assert result["vehicles"][0]["position"] == {"lat": 55.75, "lng": 37.61}
    assert result["vehicles"][0]["trail"] == [
        {"lat": 55.74, "lng": 37.60}, {"lat": 55.75, "lng": 37.61}
    ]
    assert result["vehicles"][0]["risk"]["risk_level"] == "high"
    assert [stop["id"] for stop in result["routes"][0]["stops"]] == ["11", "12"]


@pytest.mark.asyncio
async def test_dashboard_hides_stale_prediction(sqlite_session_factory):
    clock.resume_live()
    now = dt.datetime.utcnow().replace(microsecond=0)
    async with sqlite_session_factory() as session:
        session.add_all([
            TelemetryRecordORM(vehicle_id="bus-1", tr_id=7, event_time=now-dt.timedelta(minutes=1), latitude=55.75, longitude=37.61, speed=22, location_valid=True),
            ScheduleStopORM(tr_id=7, stop_id=12, seq=2, scheduled_time=now+dt.timedelta(minutes=10), latitude=55.76, longitude=37.62),
            RiskAssessmentORM(vehicle_id="bus-1", tr_id=7, target_stop_id=12, target_time_begin=now+dt.timedelta(minutes=10), predicted_at=now-dt.timedelta(days=1), predicted_delay_s=350, risk_level="high", reason="delay", source="model"),
        ])
        await session.commit()
    result = await snapshot(SimpleNamespace(session_factory=sqlite_session_factory, state_cache=EmptyCache()))
    assert result["vehicles"][0]["risk"] is None


@pytest.mark.asyncio
async def test_dashboard_hides_inactive_vehicle(sqlite_session_factory):
    clock.resume_live()
    now = dt.datetime.utcnow().replace(microsecond=0)
    async with sqlite_session_factory() as session:
        session.add(TelemetryRecordORM(
            vehicle_id="old-bus", tr_id=8, event_time=now-dt.timedelta(hours=2),
            latitude=55.75, longitude=37.61, speed=0, location_valid=True,
        ))
        await session.commit()
    result = await snapshot(SimpleNamespace(session_factory=sqlite_session_factory, state_cache=EmptyCache()))
    assert result == {"vehicles": [], "routes": []}
