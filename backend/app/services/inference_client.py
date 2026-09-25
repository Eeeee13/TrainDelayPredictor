"""ML Inference Service client.

Strategy: `HttpInferenceClient` talks to the real model container;
`HeuristicFallbackInferenceClient` is the "no model available" baseline
(`predicted_delay_s = cur_dev_s`, matching the competition's own baseline
submission). `ResilientInferenceClient` decorates the HTTP client with a
timeout + small retry budget + circuit breaker, falling back to the
heuristic on failure — this is the concrete implementation of "graceful
degradation without falling over".
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.entities import PredictItem, PredictResult, PredictionSource

logger = get_logger(__name__)


class InferenceClient(ABC):
    @abstractmethod
    async def predict_batch(self, items: list[PredictItem]) -> list[PredictResult]: ...


class HeuristicFallbackInferenceClient(InferenceClient):
    """predicted_delay_s = cur_dev_s: "things stay as bad/good as they are
    right now". This is the exact baseline the competition's
    sample_submission.csv uses (~0.40 on the scoring metric).
    """

    async def predict_batch(self, items: list[PredictItem]) -> list[PredictResult]:
        return [
            PredictResult(
                request_id=item.request_id,
                predicted_delay_s=float(item.cur_dev_s),
                confidence=None,
                source=PredictionSource.FALLBACK,
            )
            for item in items
        ]


class HttpInferenceClient(InferenceClient):
    def __init__(self, url: str, timeout_s: float) -> None:
        self._url = url
        self._timeout_s = timeout_s

    async def predict_batch(self, items: list[PredictItem]) -> list[PredictResult]:
        if not items:
            return []
        payload = {
            "items": [
                {
                    "request_id": i.request_id,
                    "tr_id": i.tr_id,
                    "T": i.T.isoformat(),
                    "cur_dev_s": i.cur_dev_s,
                    "target_stop_id": i.target_stop_id,
                    "target_time_begin": i.target_time_begin.isoformat(),
                }
                for i in items
            ]
        }
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(self._url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        by_id = {row["request_id"]: row for row in data["items"]}
        results = []
        for item in items:
            row = by_id[item.request_id]
            results.append(
                PredictResult(
                    request_id=item.request_id,
                    predicted_delay_s=float(row["predicted_delay_s"]),
                    confidence=row.get("confidence"),
                    source=PredictionSource.MODEL,
                )
            )
        return results


class _CircuitBreaker:
    """Tiny consecutive-failure circuit breaker: after N failures, stop
    hammering a dead inference service for `cooldown_s` and go straight to
    the fallback, then probe again.
    """

    def __init__(self, fail_threshold: int, cooldown_s: float) -> None:
        self._fail_threshold = fail_threshold
        self._cooldown_s = cooldown_s
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self._cooldown_s:
            self._opened_at = None  # half-open: allow a probe
            return True
        return False

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._fail_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            logger.warning("inference circuit OPEN after %d consecutive failures", self._consecutive_failures)


class ResilientInferenceClient(InferenceClient):
    def __init__(
        self,
        primary: InferenceClient,
        fallback: InferenceClient,
        max_retries: int = 1,
        fail_threshold: int = 3,
        cooldown_s: float = 15.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._max_retries = max_retries
        self._breaker = _CircuitBreaker(fail_threshold, cooldown_s)

    async def predict_batch(self, items: list[PredictItem]) -> list[PredictResult]:
        if not items:
            return []
        if not self._breaker.allow():
            return await self._fallback.predict_batch(items)

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                results = await self._primary.predict_batch(items)
                self._breaker.record_success()
                return results
            except Exception as exc:  # noqa: BLE001 - any failure degrades, doesn't crash the pipeline
                last_exc = exc
                logger.warning("inference call failed (attempt %d/%d): %s", attempt + 1, self._max_retries + 1, exc)
        self._breaker.record_failure()
        logger.warning("inference degraded to heuristic fallback: %s", last_exc)
        return await self._fallback.predict_batch(items)


def build_inference_client() -> InferenceClient:
    http_client = HttpInferenceClient(settings.inference_url, settings.inference_timeout_s)
    fallback = HeuristicFallbackInferenceClient()
    return ResilientInferenceClient(
        primary=http_client,
        fallback=fallback,
        max_retries=settings.inference_max_retries,
        fail_threshold=settings.inference_circuit_fail_threshold,
        cooldown_s=settings.inference_circuit_cooldown_s,
    )
