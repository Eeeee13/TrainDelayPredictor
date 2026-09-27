import datetime as dt

import pytest

from app.domain.entities import PredictItem, PredictResult, PredictionSource
from app.services.inference_client import (
    HeuristicFallbackInferenceClient,
    InferenceClient,
    ResilientInferenceClient,
)


def _item(cur_dev_s: int = 200) -> PredictItem:
    now = dt.datetime(2026, 1, 6, 3, 35, 0)
    return PredictItem(
        request_id="r1",
        tr_id=131672,
        T=now,
        cur_dev_s=cur_dev_s,
        target_stop_id=53700172828,
        target_time_begin=now + dt.timedelta(minutes=12),
    )


async def test_heuristic_fallback_matches_cur_dev_s():
    client = HeuristicFallbackInferenceClient()
    [result] = await client.predict_batch([_item(274)])
    assert result.predicted_delay_s == 274.0
    assert result.source == PredictionSource.FALLBACK


class _AlwaysFailsClient(InferenceClient):
    async def predict_batch(self, items):
        raise ConnectionError("model unreachable")


async def test_resilient_client_degrades_to_fallback_on_failure():
    client = ResilientInferenceClient(
        primary=_AlwaysFailsClient(),
        fallback=HeuristicFallbackInferenceClient(),
        max_retries=1,
        fail_threshold=3,
        cooldown_s=15,
    )
    [result] = await client.predict_batch([_item(150)])
    assert result.source == PredictionSource.FALLBACK
    assert result.predicted_delay_s == 150.0


async def test_resilient_client_opens_circuit_after_threshold():
    client = ResilientInferenceClient(
        primary=_AlwaysFailsClient(),
        fallback=HeuristicFallbackInferenceClient(),
        max_retries=0,
        fail_threshold=2,
        cooldown_s=999,
    )
    for _ in range(2):
        await client.predict_batch([_item()])
    assert client._breaker.allow() is False


async def test_resilient_client_passes_through_primary_success():
    class _AlwaysSucceeds(InferenceClient):
        async def predict_batch(self, items):
            return [
                PredictResult(request_id=i.request_id, predicted_delay_s=42.0, confidence=0.9, source=PredictionSource.MODEL)
                for i in items
            ]

    client = ResilientInferenceClient(primary=_AlwaysSucceeds(), fallback=HeuristicFallbackInferenceClient())
    [result] = await client.predict_batch([_item()])
    assert result.source == PredictionSource.MODEL
    assert result.predicted_delay_s == 42.0


async def test_read_timeout_is_not_retried_even_with_retry_budget():
    import httpx

    class SlowClient(InferenceClient):
        calls = 0

        async def predict_batch(self, items):
            self.calls += 1
            raise httpx.ReadTimeout("still computing")

    primary = SlowClient()
    client = ResilientInferenceClient(
        primary, HeuristicFallbackInferenceClient(), max_retries=2,
        fail_threshold=2, cooldown_s=999,
    )
    for _ in range(3):
        [result] = await client.predict_batch([_item(150)])
        assert result.source == PredictionSource.FALLBACK
        assert result.predicted_delay_s == 150
    assert primary.calls == 2  # One per batch, then the circuit blocks the third.
