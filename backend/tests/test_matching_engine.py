import datetime as dt

from app.domain.entities import ScheduleStop, TelemetryRecord
from app.services.matching_engine import MatchingEngine


def _stop(seq: int, minutes_from: dt.datetime, lat: float, lon: float) -> ScheduleStop:
    return ScheduleStop(tr_id=1, stop_id=100 + seq, seq=seq, scheduled_time=minutes_from, latitude=lat, longitude=lon)


def test_deviation_computed_on_stop_match():
    now = dt.datetime(2026, 1, 6, 3, 30, 0)
    stops = [_stop(0, now, 55.75, 37.61), _stop(1, now + dt.timedelta(minutes=5), 55.76, 37.62)]
    engine = MatchingEngine(stop_match_radius_m=100)

    late_arrival = now + dt.timedelta(seconds=180)
    telemetry = TelemetryRecord(
        vehicle_id="bus-1", event_time=late_arrival, latitude=55.75, longitude=37.61, speed=0.0, tr_id=1
    )
    state = engine.update(None, telemetry, stops)

    assert state.cur_dev_s == 180
    assert state.last_matched_stop_id == 100


def test_deviation_carried_forward_between_stops():
    now = dt.datetime(2026, 1, 6, 3, 30, 0)
    stops = [_stop(0, now, 55.75, 37.61), _stop(1, now + dt.timedelta(minutes=5), 55.76, 37.62)]
    engine = MatchingEngine(stop_match_radius_m=100)

    matched = engine.update(
        None,
        TelemetryRecord(vehicle_id="bus-1", event_time=now + dt.timedelta(seconds=120), latitude=55.75, longitude=37.61, speed=0.0, tr_id=1),
        stops,
    )
    assert matched.cur_dev_s == 120

    # far from any stop -> no new match, deviation should be unchanged
    mid_segment = engine.update(
        matched,
        TelemetryRecord(vehicle_id="bus-1", event_time=now + dt.timedelta(seconds=200), latitude=55.755, longitude=37.615, speed=8.0, tr_id=1),
        stops,
    )
    assert mid_segment.cur_dev_s == 120
    assert mid_segment.last_matched_stop_id == 100


def test_next_target_only_looks_forward():
    now = dt.datetime(2026, 1, 6, 3, 30, 0)
    stops = [_stop(0, now, 55.75, 37.61), _stop(1, now + dt.timedelta(minutes=5), 55.76, 37.62)]
    engine = MatchingEngine()
    state = engine.update(
        None,
        TelemetryRecord(vehicle_id="bus-1", event_time=now, latitude=55.75, longitude=37.61, speed=0.0, tr_id=1),
        stops,
    )
    target = engine.next_target(state, stops)
    assert target is not None
    assert target.stop_id == 101  # stop 1, not stop 0 again
