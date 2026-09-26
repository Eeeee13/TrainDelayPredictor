"""Matching Engine: turns raw telemetry + the reference schedule into
`cur_dev_s` — the non-ML "how far off schedule is this vehicle right now"
signal that both feeds the ML model as a feature and serves as the
degradation fallback prediction on its own.

Approach: on every telemetry point, look for a schedule stop of the
vehicle's current trip within `stop_match_radius_m`. A match means "the
vehicle is passing/at this stop now" -> deviation = actual time - scheduled
time for that stop. Between stops (most packets), there's no new ground
truth, so we carry the last computed deviation forward rather than
guessing — this mirrors real-world dispatcher tooling and avoids
inventing a spurious drift model with no data to back it.
"""
from __future__ import annotations

import datetime as dt

from app.core.config import settings
from app.domain.entities import ScheduleStop, TelemetryRecord, VehicleState
from app.services.geo import haversine_m

_STATIONARY_SPEED_KMH = 2.0  # telemetry speed is in km/h


class MatchingEngine:
    def __init__(self, stop_match_radius_m: float | None = None) -> None:
        self._radius_m = stop_match_radius_m or settings.stop_match_radius_m

    def update(
        self,
        prev: VehicleState | None,
        telemetry: TelemetryRecord,
        trip_stops: list[ScheduleStop],
    ) -> VehicleState:
        state = prev or VehicleState(vehicle_id=telemetry.vehicle_id)

        # smoothed segment speed (EMA) - a candidate feature / diagnostic
        alpha = 0.4
        state.avg_speed_segment = (
            telemetry.speed if state.avg_speed_segment == 0.0 else alpha * telemetry.speed + (1 - alpha) * state.avg_speed_segment
        )

        if telemetry.location_valid and telemetry.speed <= _STATIONARY_SPEED_KMH:
            state.stationary_since = state.stationary_since or telemetry.event_time
        else:
            state.stationary_since = None

        matched = self._match_stop(telemetry, trip_stops, state.last_matched_seq) if telemetry.location_valid else None
        if matched is not None:
            deviation = (telemetry.event_time - matched.scheduled_time).total_seconds()
            state.cur_dev_s = int(round(deviation))
            state.last_matched_stop_id = matched.stop_id
            state.last_matched_seq = matched.seq
        # else: keep state.cur_dev_s as-is (carry forward last known deviation)

        state.tr_id = telemetry.tr_id or state.tr_id
        state.last_event_time = telemetry.event_time
        if telemetry.location_valid:
            state.last_lat = telemetry.latitude
            state.last_lon = telemetry.longitude
        state.last_speed = telemetry.speed
        state.updated_at = telemetry.event_time
        return state

    def _match_stop(
        self, telemetry: TelemetryRecord, trip_stops: list[ScheduleStop], last_matched_seq: int
    ) -> ScheduleStop | None:
        """Only ever match forward along the trip (seq > last matched) so a
        vehicle can't be re-matched to a stop it already passed just
        because it's geographically close again later (loop routes).
        """
        candidates = [s for s in trip_stops if s.seq > last_matched_seq and s.latitude is not None
                      and abs((s.scheduled_time - telemetry.event_time).total_seconds()) <= 12 * 60]
        best: ScheduleStop | None = None
        best_dist = self._radius_m
        for stop in candidates:
            dist = haversine_m(telemetry.latitude, telemetry.longitude, stop.latitude, stop.longitude)
            if dist <= best_dist:
                best = stop
                best_dist = dist
        return best

    def next_target(self, state: VehicleState, trip_stops: list[ScheduleStop]) -> ScheduleStop | None:
        """The next stop still ahead of the vehicle on its current trip -
        the natural `target_stop_id` for a forecast."""
        upcoming = [s for s in trip_stops if s.seq > state.last_matched_seq]
        if not upcoming:
            return None
        return min(upcoming, key=lambda s: s.seq)
