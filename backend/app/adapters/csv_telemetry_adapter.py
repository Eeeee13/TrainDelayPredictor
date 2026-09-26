"""Adapters for the organizer's decoded NDTP CSV and timetable CSV."""
from __future__ import annotations

import re
from collections.abc import Iterator

import pandas as pd

from app.domain.entities import ScheduleStop, TelemetryRecord

_POINT = re.compile(r"POINT \(([-\d.]+) ([-\d.]+)\)")


def read_traffic_csv(path: str) -> Iterator[TelemetryRecord]:
    df = pd.read_csv(path, usecols=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"])
    for row in df.itertuples(index=False):
        valid = str(row.location_valid).lower() == "true" and pd.notna(row.lon) and pd.notna(row.lat)
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
