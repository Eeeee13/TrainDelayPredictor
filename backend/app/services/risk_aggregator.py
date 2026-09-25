"""RiskAggregator: predicted delay (seconds) -> dispatcher-facing risk
level + a plain-language reason. Reason detection stays pattern-level
(speed drop / prolonged stop / accumulated drift) rather than a full
root-cause model — that's explicitly a bonus ("выявление паттернов"), and
a simple, explainable heuristic is more useful to a dispatcher than a
black box anyway.
"""
from __future__ import annotations

import datetime as dt

from app.core.config import settings
from app.domain.entities import PredictItem, PredictResult, RiskAssessment, RiskLevel, VehicleState

_STATIONARY_REASON_THRESHOLD_S = 90
_LOW_SPEED_MS = 2.0


class RiskAggregator:
    def __init__(self, medium_threshold_s: int | None = None, high_threshold_s: int | None = None) -> None:
        self._medium = medium_threshold_s if medium_threshold_s is not None else settings.risk_threshold_medium_s
        self._high = high_threshold_s if high_threshold_s is not None else settings.risk_threshold_high_s

    def level_for(self, predicted_delay_s: float) -> RiskLevel:
        magnitude = abs(predicted_delay_s)
        if magnitude >= self._high:
            return RiskLevel.HIGH
        if magnitude >= self._medium:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _reason_for(self, state: VehicleState, predicted_delay_s: float) -> str:
        if predicted_delay_s <= -self._medium:
            return "опережение графика"
        if state.stationary_since is not None:
            stalled_s = 0.0
            if state.last_event_time is not None:
                stalled_s = (state.last_event_time - state.stationary_since).total_seconds()
            if stalled_s >= _STATIONARY_REASON_THRESHOLD_S:
                return "длительная стоянка / простой"
        if state.avg_speed_segment and state.avg_speed_segment < _LOW_SPEED_MS:
            return "аномальное снижение скорости"
        if predicted_delay_s >= self._medium:
            return "накопленное отставание от графика"
        return "в пределах нормы"

    def assess(
        self,
        state: VehicleState,
        item: PredictItem,
        result: PredictResult,
        now: dt.datetime,
    ) -> RiskAssessment:
        level = self.level_for(result.predicted_delay_s)
        reason = self._reason_for(state, result.predicted_delay_s)
        return RiskAssessment(
            vehicle_id=state.vehicle_id,
            tr_id=item.tr_id,
            target_stop_id=item.target_stop_id,
            target_time_begin=item.target_time_begin,
            predicted_at=now,
            predicted_delay_s=result.predicted_delay_s,
            risk_level=level,
            reason=reason,
            source=result.source,
            confidence=result.confidence,
        )
