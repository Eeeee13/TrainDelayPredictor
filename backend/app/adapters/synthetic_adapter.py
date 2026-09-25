"""Synthetic telemetry/schedule generator - no external files needed.
Used for local development and demoing the pipeline before/without the
real dataset or the NDTP emulator.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from app.domain.entities import ScheduleStop, TelemetryRecord

_LAT0, _LON0 = 55.751244, 37.618423  # Moscow, arbitrary start point
_STOP_SPACING_DEG = 0.004  # ~350-450m between stops


def generate_schedule(tr_id: int, n_stops: int = 10, start: dt.datetime | None = None, stop_interval_s: int = 180) -> list[ScheduleStop]:
    start = start or dt.datetime.utcnow() + dt.timedelta(minutes=2)
    stops = []
    for seq in range(n_stops):
        stops.append(
            ScheduleStop(
                tr_id=tr_id,
                stop_id=tr_id * 1000 + seq,
                seq=seq,
                scheduled_time=start + dt.timedelta(seconds=seq * stop_interval_s),
                latitude=_LAT0 + seq * _STOP_SPACING_DEG,
                longitude=_LON0 + seq * _STOP_SPACING_DEG * 0.6,
            )
        )
    return stops


def replay_vehicle(
    vehicle_id: str,
    tr_id: int,
    stops: list[ScheduleStop],
    delay_bias_s: float = 0.0,
    packet_interval_s: int = 13,
) -> Iterator[TelemetryRecord]:
    """Yields telemetry points walking the vehicle along `stops`, arriving
    at each stop `delay_bias_s` seconds late (negative = early), so you can
    synthesize both healthy and at-risk trips.
    """
    if not stops:
        return
    t = stops[0].scheduled_time - dt.timedelta(minutes=1)
    for i, stop in enumerate(stops):
        arrival = stop.scheduled_time + dt.timedelta(seconds=delay_bias_s)
        prev = stops[i - 1] if i > 0 else None
        segment_start = t
        n_points = max(1, int((arrival - segment_start).total_seconds() // packet_interval_s))
        for p in range(n_points):
            frac = p / max(n_points, 1)
            lat = (prev.latitude if prev else stop.latitude) + frac * (stop.latitude - (prev.latitude if prev else stop.latitude))
            lon = (prev.longitude if prev else stop.longitude) + frac * (stop.longitude - (prev.longitude if prev else stop.longitude))
            event_time = segment_start + dt.timedelta(seconds=p * packet_interval_s)
            yield TelemetryRecord(
                vehicle_id=vehicle_id,
                event_time=event_time,
                latitude=lat,
                longitude=lon,
                speed=8.0,
                door_open=False,
                tr_id=tr_id,
            )
        yield TelemetryRecord(
            vehicle_id=vehicle_id,
            event_time=arrival,
            latitude=stop.latitude,
            longitude=stop.longitude,
            speed=0.0,
            door_open=True,
            tr_id=tr_id,
        )
        t = arrival
