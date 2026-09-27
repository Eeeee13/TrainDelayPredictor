"""Prepared schedule snapshots, invalidated by a transactional DB revision.

Snapshots are treated as immutable by readers. Each request checks the revision
in the same REPEATABLE READ transaction that supplies its input rows.
"""
from dataclasses import dataclass
from threading import RLock

import pandas as pd
from sqlalchemy import text

from model.features import load_schedule
from model.timing import current_timings, measure, measured_lock


@dataclass(frozen=True)
class ScheduleSnapshot:
    frame: pd.DataFrame
    by_trip: dict
    known: frozenset
    revision: int | None = None


def read_schedule(conn, tr_ids=None, revision=None):
    query = ("SELECT tr_id, stop_id AS tt_action_item_id, scheduled_time AS time_begin, "
             "longitude, latitude, manual_fill FROM schedule_stops")
    params = {}
    if tr_ids is not None:
        params = {f"tr_{n}": tr for n, tr in enumerate(tr_ids)}
        query += " WHERE tr_id IN (" + ",".join(f":{key}" for key in params) + ")"
    with measure("db_schedule_ms"):
        rows = conn.execute(text(query), params).tuples().all()
    with measure("schedule_frame_ms"):
        frame = pd.DataFrame(rows, columns=["tr_id", "tt_action_item_id", "time_begin",
                                             "longitude", "latitude", "manual_fill"])
        frame["time_begin"] = pd.to_datetime(frame.time_begin, utc=True).dt.tz_convert("Europe/Moscow").dt.tz_localize(None)
    with measure("load_schedule_ms"):
        prepared = load_schedule(frame) if len(frame) else {}
        known = frozenset(zip(frame.tr_id.astype(int), frame.tt_action_item_id.astype(int), frame.time_begin))
    timings = current_timings.get()
    if timings is not None:
        timings["schedule_rows_loaded"] = len(rows)
    return ScheduleSnapshot(frame, prepared, known, revision)


class ScheduleCache:
    def __init__(self):
        self._lock = RLock()
        self._snapshot = None

    def get(self, conn):
        with measure("schedule_revision_ms"):
            revision = conn.execute(text("SELECT revision FROM schedule_revision WHERE singleton")).scalar_one()
        with measured_lock(self._lock, "schedule_cache_wait_ms"):
            hit = self._snapshot is not None and self._snapshot.revision == revision
            timings = current_timings.get()
            if timings is not None:
                timings["schedule_cache_hit"] = hit
                timings["schedule_revision"] = revision
                timings["schedule_rows_loaded"] = 0
            if hit:
                return self._snapshot
            snapshot = read_schedule(conn, revision=revision)
            # An older in-flight transaction must not evict a newer snapshot.
            if self._snapshot is None or revision > self._snapshot.revision:
                self._snapshot = snapshot
            return snapshot
