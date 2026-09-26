import datetime as dt

import pytest
from sqlalchemy import select

from app.api.routes.predictions import _to_out
from app.api.routes.dashboard import snapshot
from app.db.models import RiskAssessmentORM, PredictionLogORM
from app.domain.entities import PredictItem, PredictResult, PredictionSource, VehicleState, TelemetryRecord
from app.repositories.prediction_repo import PredictionRepository
from app.repositories.telemetry_repo import TelemetryRepository
from app.services.risk_aggregator import RiskAggregator
from app.services.inference_client import _probability, HeuristicFallbackInferenceClient
from app.services.state_cache import StateCache
from types import SimpleNamespace


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-0.1,1.1])
def test_invalid_probability(value):
    with pytest.raises(ValueError):_probability(value)


async def test_probability_rest_storage_snapshot(sqlite_session_factory):
    now=dt.datetime.utcnow()
    item=PredictItem('req',1,now,130,10,now+dt.timedelta(minutes=12))
    result=PredictResult('req',180,None,PredictionSource.MODEL,delay_probability=0.78)
    state=VehicleState('1',tr_id=1)
    risk=RiskAggregator().assess(state,item,result,now)
    assert risk.to_dict()['delay_probability']==0.78
    assert _to_out(risk).delay_probability==0.78
    async with sqlite_session_factory() as session:
        await PredictionRepository(session).upsert_risk(risk)
        await TelemetryRepository(session).bulk_upsert([TelemetryRecord('1',now,55.7,37.6,20,tr_id=1)])
        stored=(await session.execute(select(RiskAssessmentORM))).scalar_one()
        assert stored.delay_probability==0.78
    # Empty cache forces the dashboard to use persisted probability.
    container=SimpleNamespace(session_factory=sqlite_session_factory,state_cache=StateCache())
    assert (await snapshot(container))['vehicles'][0]['risk']['delay_probability']==0.78
    fallback=(await HeuristicFallbackInferenceClient().predict_batch([item]))[0]
    assert fallback.delay_probability is None
    late=PredictItem('late',1,now,130,10,now+dt.timedelta(minutes=2))
    assert await HeuristicFallbackInferenceClient().predict_batch([late])==[]
