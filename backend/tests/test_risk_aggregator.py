import datetime as dt

from app.domain.entities import PredictItem, PredictResult, PredictionSource, RiskLevel, VehicleState
from app.services.risk_aggregator import RiskAggregator


def _predict_item() -> PredictItem:
    now = dt.datetime(2026, 1, 6, 3, 35, 0)
    return PredictItem(
        request_id="r", tr_id=1, T=now, cur_dev_s=0, target_stop_id=1, target_time_begin=now + dt.timedelta(minutes=12)
    )


def test_levels_respect_thresholds():
    agg = RiskAggregator(medium_threshold_s=120, high_threshold_s=300)
    assert agg.level_for(50) == RiskLevel.LOW
    assert agg.level_for(150) == RiskLevel.MEDIUM
    assert agg.level_for(400) == RiskLevel.HIGH
    assert agg.level_for(-400) == RiskLevel.HIGH  # magnitude matters, not just lateness


def test_assess_builds_full_assessment():
    agg = RiskAggregator(medium_threshold_s=120, high_threshold_s=300)
    state = VehicleState(vehicle_id="bus-1", tr_id=1, cur_dev_s=310)
    item = _predict_item()
    result = PredictResult(request_id="r", predicted_delay_s=310, confidence=0.7, source=PredictionSource.MODEL)

    assessment = agg.assess(state, item, result, now=item.T)

    assert assessment.risk_level == RiskLevel.HIGH
    assert assessment.vehicle_id == "bus-1"
    assert assessment.source == PredictionSource.MODEL
    assert assessment.confidence == 0.7
