"""The single in-memory source of truth for "what's happening right now".

Everything here is cheap to read/write and single-process only. Postgres
holds the durable/audit copy; this is what the hot path (feature building,
scheduling, `GET /risk`) actually touches, because a DB round trip per
NDTP packet per vehicle would blow the latency budget at fleet scale.

Not thread-safe by design — it's only ever touched from the asyncio event
loop, never from a separate OS thread.
"""
from __future__ import annotations

import datetime as dt

from app.domain.entities import RiskAssessment, VehicleState


class StateCache:
    def __init__(self) -> None:
        self.vehicles: dict[str, VehicleState] = {}
        self.risk: dict[str, RiskAssessment] = {}  # keyed by vehicle_id
        # idempotency guard: which (tr_id, target_stop_id) pairs have already
        # received their first (on-time) prediction this run
        self._predicted_pairs: set[tuple[int, int]] = set()

    # --- vehicle state ---------------------------------------------------
    def get_vehicle(self, vehicle_id: str) -> VehicleState | None:
        return self.vehicles.get(vehicle_id)

    def put_vehicle(self, state: VehicleState) -> None:
        self.vehicles[state.vehicle_id] = state

    def active_vehicles(self, now: dt.datetime, stale_after_s: int) -> list[VehicleState]:
        return [
            v
            for v in self.vehicles.values()
            if v.last_event_time is not None and 0 <= (now - v.last_event_time).total_seconds() <= stale_after_s
        ]

    # --- risk snapshot -----------------------------------------------------
    def put_risk(self, assessment: RiskAssessment) -> None:
        self.risk[assessment.vehicle_id] = assessment

    def all_risk(self) -> list[RiskAssessment]:
        return list(self.risk.values())

    def get_risk(self, vehicle_id: str) -> RiskAssessment | None:
        return self.risk.get(vehicle_id)

    # --- idempotency -----------------------------------------------------
    def mark_predicted(self, tr_id: int, target_stop_id: int) -> None:
        self._predicted_pairs.add((tr_id, target_stop_id))

    def already_predicted(self, tr_id: int, target_stop_id: int) -> bool:
        return (tr_id, target_stop_id) in self._predicted_pairs
