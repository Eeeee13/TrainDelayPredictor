"""Trip metrics and the PDF built from them, without calling the model."""
import datetime as dt

import pytest

from app.db.models import ScheduleStopORM, TelemetryRecordORM
from app.services.report_llm import ReportUnavailable
from app.services.report_pdf import bus_variant, render_trip_pdf, stop_tick_indexes
from app.services.trip_metrics import build_trip_metrics


def _point(when: dt.datetime, lat: float, lon: float, speed: float) -> TelemetryRecordORM:
    return TelemetryRecordORM(
        vehicle_id="131672", event_time=when, latitude=lat, longitude=lon,
        speed=speed, door_open=False, location_valid=True, tr_id=131672,
    )


def test_trip_metrics_cover_speed_stops_and_delay():
    start = dt.datetime(2026, 1, 6, 8, 0)
    telemetry = [
        _point(start, 55.751244, 37.618423, 0),
        _point(start + dt.timedelta(minutes=3), 55.751244, 37.618423, 0),
        _point(start + dt.timedelta(minutes=10), 55.755000, 37.622000, 36),
    ]
    stops = [ScheduleStopORM(
        tr_id=131672, stop_id=10, seq=0, scheduled_time=start - dt.timedelta(minutes=2),
        latitude=55.751244, longitude=37.618423, manual_fill=False,
    )]
    metrics = build_trip_metrics("131672", telemetry, stops, [], [])
    assert metrics is not None
    assert metrics["telemetry"]["points"] == 3
    assert metrics["telemetry"]["stopped_episodes"] == 1
    assert metrics["telemetry"]["distance_km"] > 0
    assert metrics["schedule"]["stops_passed"] == 1
    assert metrics["schedule"]["matched_stops"][0]["delay_s"] == 120
    assert metrics["series"]["speed"][-1]["speed_kmh"] == 36.0


def test_trip_metrics_without_telemetry_is_empty():
    assert build_trip_metrics("131672", [], [], [], []) is None


def test_stop_numbers_are_spaced_when_the_route_is_long():
    labels = [str(seq) for seq in range(1, 41)]
    ticks = stop_tick_indexes(labels)
    assert ticks[0] == 0
    assert ticks[-1] == len(labels) - 1
    assert all(right - left >= 3 for left, right in zip(ticks, ticks[1:]))


def test_bus_photo_follows_the_dashboard_split():
    assert bus_variant("131672") == "v1"
    assert bus_variant("4") == "v2"


def test_pdf_contains_analysis_pages():
    start = dt.datetime(2026, 1, 6, 8, 0)
    telemetry = [
        _point(start, 55.751244, 37.618423, 20),
        _point(start + dt.timedelta(minutes=5), 55.753000, 37.620000, 30),
    ]
    metrics = build_trip_metrics("131672", telemetry, [], [], [])
    pdf = render_trip_pdf(metrics, "Краткий вывод.\nСкорость ровная.")
    assert pdf.startswith(b"%PDF")
    assert b"/Subtype /Image" in pdf
    assert len(pdf) > 1000


def test_model_call_requires_api_key(monkeypatch):
    from app.services import report_llm

    monkeypatch.setattr(report_llm.yandex_settings, "api_key", "")
    with pytest.raises(ReportUnavailable):
        report_llm._complete({"vehicle_id": "1"})
