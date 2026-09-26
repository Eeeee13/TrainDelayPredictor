"""Standalone stand-in for the ML Inference Service container.

Implements the exact contract `HttpInferenceClient` calls
(`POST /predict` with a batch of items), so the backend can be developed,
demoed and load-tested end-to-end before the real model image exists.

Wiring in the real model is meant to be a one-line change: replace
`_stub_predict` with a call to `predictor.predict(...)` per item, e.g.

    from your_model_package import predictor
    delay = predictor.predict(
        tr_id=item.tr_id, T=item.T, cur_dev_s=item.cur_dev_s,
        target_stop_id=item.target_stop_id, target_time_begin=item.target_time_begin,
    )

keeping the request/response shape below unchanged so the backend needs no
changes at all when the real container replaces this one.
"""
from __future__ import annotations

import datetime as dt

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="inference-stub")


class PredictItemIn(BaseModel):
    request_id: str
    tr_id: int
    T: dt.datetime
    cur_dev_s: int
    target_stop_id: int
    target_time_begin: dt.datetime


class PredictBatchIn(BaseModel):
    items: list[PredictItemIn]


class PredictItemOut(BaseModel):
    request_id: str
    predicted_delay_s: float
    confidence: float | None = None


class PredictBatchOut(BaseModel):
    items: list[PredictItemOut]


def _stub_predict(item: PredictItemIn) -> float:
    """Placeholder "model": current deviation, decayed slightly toward zero
    the further out the target is (a real model would obviously do much
    better - this only exists to prove the contract and give non-trivial,
    non-identical-to-fallback numbers for demoing).
    """
    lead_s = max((item.target_time_begin - item.T).total_seconds(), 1.0)
    decay = 0.9 if lead_s < 900 else 0.8
    return round(item.cur_dev_s * decay, 1)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mode": "stub"}


@app.post("/predict", response_model=PredictBatchOut)
async def predict(batch: PredictBatchIn) -> PredictBatchOut:
    return PredictBatchOut(
        items=[
            PredictItemOut(request_id=item.request_id, predicted_delay_s=_stub_predict(item), confidence=0.5)
            for item in batch.items
        ]
    )
