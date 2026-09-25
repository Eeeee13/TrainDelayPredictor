"""Converts the competition's `traffic.csv` / `schedule.csv` dataset files
into domain entities.

IMPORTANT: the exact column names of the hackathon dataset are not baked
into this repo (the dataset itself isn't bundled here — see the
organizers' link). The constants below are this adapter's *only* contract
with the file format: point them at the real headers once you have the
CSVs and nothing else in the pipeline needs to change (Ports & Adapters —
MatchingEngine/RiskAggregator/API never see a CSV row).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pandas as pd

from app.domain.entities import ScheduleStop, TelemetryRecord

# --- adjust these to the real dataset headers -----------------------------
TRAFFIC_COLUMNS = dict(
    vehicle_id="vehicle_id",
    event_time="event_time",
    latitude="lat",
    longitude="lon",
    speed="speed",
    door_open="door_open",
    tr_id="tr_id",
)
SCHEDULE_COLUMNS = dict(
    tr_id="tr_id",
    stop_id="stop_id",
    seq="seq",
    scheduled_time="scheduled_time",
    latitude="lat",
    longitude="lon",
)
# ---------------------------------------------------------------------------


def read_traffic_csv(path: str) -> Iterator[TelemetryRecord]:
    df = pd.read_csv(path)
    c = TRAFFIC_COLUMNS
    for row in df.itertuples(index=False):
        r = row._asdict()
        yield TelemetryRecord(
            vehicle_id=str(r[c["vehicle_id"]]),
            event_time=pd.to_datetime(r[c["event_time"]]).to_pydatetime(),
            latitude=float(r[c["latitude"]]),
            longitude=float(r[c["longitude"]]),
            speed=float(r.get(c["speed"], 0.0) or 0.0),
            door_open=bool(r.get(c["door_open"], False)),
            tr_id=int(r[c["tr_id"]]) if pd.notna(r.get(c["tr_id"])) else None,
        )


def read_schedule_csv(path: str) -> Iterator[ScheduleStop]:
    df = pd.read_csv(path)
    c = SCHEDULE_COLUMNS
    for row in df.itertuples(index=False):
        r = row._asdict()
        yield ScheduleStop(
            tr_id=int(r[c["tr_id"]]),
            stop_id=int(r[c["stop_id"]]),
            seq=int(r[c["seq"]]),
            scheduled_time=pd.to_datetime(r[c["scheduled_time"]]).to_pydatetime(),
            latitude=float(r[c["latitude"]]) if pd.notna(r.get(c["latitude"])) else None,
            longitude=float(r[c["longitude"]]) if pd.notna(r.get(c["longitude"])) else None,
        )
