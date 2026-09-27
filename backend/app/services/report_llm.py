"""Asks the Yandex-hosted model to explain a trip from aggregated metrics."""
from __future__ import annotations

import asyncio
import json

from openai import OpenAI

from app.core.config import yandex_settings

_INSTRUCTIONS = (
    "Ты аналитик диспетчерской службы городского транспорта. "
    "По JSON с метриками одного рейса напиши разбор на русском языке. "
    "Используй только числа и факты из JSON, ничего не додумывай. "
    "Если прогнозов или пройденных остановок нет, так и напиши. "
    "Структура: краткий вывод; скорость и стоянки; соблюдение расписания; "
    "прогноз задержки; что сделать диспетчеру. "
    "Обычный текст, без markdown и без символа #."
)


class ReportUnavailable(RuntimeError):
    pass


def _compact(metrics: dict) -> dict:
    """Drop the chart series; the model only needs the aggregates."""
    payload = {key: value for key, value in metrics.items() if key != "series"}
    stops = payload.get("schedule", {}).get("matched_stops", [])
    if len(stops) > 12:
        payload["schedule"] = {**payload["schedule"], "matched_stops": stops[:6] + stops[-6:]}
    return payload


def _complete(metrics: dict) -> str:
    settings = yandex_settings
    if not settings.api_key:
        raise ReportUnavailable("Не задан YANDEX_CLOUD_API_KEY")
    client = OpenAI(
        api_key=settings.api_key,
        base_url="https://ai.api.cloud.yandex.net/v1",
        project=settings.folder,
        timeout=90,
    )
    response = client.responses.create(
        model=f"gpt://{settings.folder}/{settings.model}",
        temperature=0.3,
        instructions=_INSTRUCTIONS,
        input=json.dumps(_compact(metrics), ensure_ascii=False),
        max_output_tokens=2048,
        store=True,
        truncation="disabled",
    )
    text = (getattr(response, "output_text", None) or "").strip()
    if not text:
        raise ReportUnavailable("Модель вернула пустой разбор")
    return text


async def analyze_trip(metrics: dict) -> str:
    return await asyncio.to_thread(_complete, metrics)
