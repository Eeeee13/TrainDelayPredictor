"""FeatureBuilder: assembles the exact request the ML model expects.

Kept as a separate, single-purpose class (rather than inlining this in the
scheduler) because it's the one place that has to stay byte-for-byte in
sync with the model's contract:

    predictor.predict(tr_id, T, cur_dev_s, target_stop_id, target_time_begin)
"""
from __future__ import annotations

import datetime as dt
import uuid

from app.domain.entities import PredictItem, ScheduleStop, VehicleState


class FeatureBuilder:
    def build(self, state: VehicleState, target: ScheduleStop, now: dt.datetime) -> PredictItem:
        assert state.tr_id is not None, "vehicle state has no trip id yet"
        return PredictItem(
            request_id=str(uuid.uuid4()),
            tr_id=state.tr_id,
            T=now,
            cur_dev_s=state.cur_dev_s,
            target_stop_id=target.stop_id,
            target_time_begin=target.scheduled_time,
        )
