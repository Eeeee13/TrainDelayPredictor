"""Adapters for the organizer's decoded NDTP CSV and timetable CSV."""
from __future__ import annotations

import re
import math
from collections.abc import Iterator

import pandas as pd

from app.domain.entities import ScheduleStop, TelemetryRecord

_POINT = re.compile(r"POINT \(([-\d.]+) ([-\d.]+)\)")

# Match the GPS cleaning rules in training/train.py and model/features.py.
_SPOOF_CENTER = (37.4149, 55.9731)
_SPOOF_RADIUS_M = 3000.0
_MAX_JUMP_KMH = 150.0


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return math.hypot((lon1 - lon2) * 62_800.0, (lat1 - lat2) * 111_200.0)


def read_traffic_csv(path: str) -> Iterator[TelemetryRecord]:
    df = pd.read_csv(path, usecols=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"])
    df["event_time"] = pd.to_datetime(df["event_time"], format="mixed")
    df = df.sort_values("event_time", kind="stable")
    last_valid = {}
    for row in df.itertuples(index=False):
        valid = str(row.location_valid).lower() == "true" and pd.notna(row.lon) and pd.notna(row.lat)
        if valid:
            valid = math.isfinite(row.lon) and math.isfinite(row.lat)
        if valid:
            radius = _distance_m(row.lon, row.lat, *_SPOOF_CENTER)
            valid = not 0.0 < radius < _SPOOF_RADIUS_M
        if valid:
            # Training uses whole seconds and compares to the last accepted fix.
            seconds = row.event_time.value // 1_000_000_000
            previous = last_valid.get(row.tr_id)
            if previous is not None:
                lon, lat, timestamp = previous
                valid = (_distance_m(row.lon, row.lat, lon, lat)
                         / max(seconds - timestamp, 1) * 3.6 <= _MAX_JUMP_KMH)
            if valid:
                last_valid[row.tr_id] = (row.lon, row.lat, seconds)
        yield TelemetryRecord(
            vehicle_id=str(row.tr_id), tr_id=int(row.tr_id),
            event_time=pd.Timestamp(row.event_time).to_pydatetime(),
            latitude=float(row.lat) if valid else 0.0,
            longitude=float(row.lon) if valid else 0.0,
            speed=float(row.speed) if pd.notna(row.speed) else 0.0,
            location_valid=valid,
        )


def read_schedule_csv(path: str) -> Iterator[ScheduleStop]:
    df = pd.read_csv(path)
    df["time_begin"] = pd.to_datetime(df["time_begin"], format="mixed")
    df = df.sort_values(["tr_id", "time_begin", "tt_action_item_id"])
    df["seq"] = df.groupby("tr_id").cumcount()
    for row in df.itertuples(index=False):
        match = _POINT.fullmatch(str(row.geom))
        yield ScheduleStop(
            tr_id=int(row.tr_id), stop_id=int(row.tt_action_item_id), seq=int(row.seq),
            scheduled_time=row.time_begin.to_pydatetime(),
            latitude=float(match.group(2)) if match else None,
            longitude=float(match.group(1)) if match else None,
            manual_fill=str(row.manual_fill).lower() == "true",
        )
