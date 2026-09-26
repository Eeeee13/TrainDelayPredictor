"""Minimal pub/sub port with two implementations: an in-process asyncio
queue bus (zero external deps, always works) and a Redis Streams bus
(gives the Backend<->ML boundary a real, restart-safe queue and matches
the topic layout the architecture doc asks for: telemetry / features /
predictions / alerts).

Deliberately a tiny surface (publish + subscribe) rather than a generic
message-broker wrapper — this is the one seam we actually need, per the
"patterns without fanaticism" brief.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)

TOPIC_TELEMETRY = "telemetry"
TOPIC_FEATURES = "features"
TOPIC_PREDICTIONS = "predictions"
TOPIC_ALERTS = "alerts"


class EventBus(Protocol):
    async def publish(self, topic: str, payload: dict) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[dict]: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class MemoryEventBus:
    """asyncio.Queue-per-topic fan-out bus. No persistence, no cross-process
    delivery - the safety net when Redis isn't reachable, and good enough
    for a single backend instance.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic: str, payload: dict) -> None:
        for q in self._subscribers.get(topic, []):
            q.put_nowait(payload)

    async def subscribe(self, topic: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue(maxsize=10_000)
        self._subscribers.setdefault(topic, []).append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers[topic].remove(q)


class RedisStreamsEventBus:
    """XADD/XREAD-based bus. One consumer group per topic named
    "backend", so multiple worker instances could share the load later
    without re-architecting.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis = None
        self._group = "backend"

    async def start(self) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        await self._redis.ping()

    async def stop(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    async def _ensure_group(self, topic: str) -> None:
        try:
            await self._redis.xgroup_create(name=topic, groupname=self._group, id="0", mkstream=True)
        except Exception as exc:  # BUSYGROUP if it already exists
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, topic: str, payload: dict) -> None:
        await self._redis.xadd(topic, {"data": json.dumps(payload, default=str)}, maxlen=100_000, approximate=True)

    async def subscribe(self, topic: str) -> AsyncIterator[dict]:
        await self._ensure_group(topic)
        consumer_name = f"c-{id(self)}"
        while True:
            # A crashed consumer leaves unacknowledged entries in the group.
            pending = await self._redis.xautoclaim(topic, self._group, consumer_name,
                                                   min_idle_time=5000, start_id="0-0", count=100)
            if pending[1]:
                resp = [(topic, pending[1])]
            else:
                resp = await self._redis.xreadgroup(
                    groupname=self._group,
                    consumername=consumer_name,
                    streams={topic: ">"},
                    count=100,
                    block=2000,
                )
            if not resp:
                continue
            for _stream, entries in resp:
                for entry_id, fields in entries:
                    yield json.loads(fields["data"])
                    await self._redis.xack(topic, self._group, entry_id)


async def build_event_bus(redis_url: str | None, use_redis: bool) -> EventBus:
    """Try Redis Streams first when configured; fall back to the in-process
    bus on any connection failure so the service still boots (degradation
    without falling over — same philosophy as the inference client).
    """
    if use_redis and redis_url:
        bus = RedisStreamsEventBus(redis_url)
        try:
            await bus.start()
            logger.info("event bus: using Redis Streams at %s", redis_url)
            return bus
        except Exception as exc:  # noqa: BLE001
            logger.warning("event bus: Redis unavailable (%s), falling back to in-memory bus", exc)
    bus = MemoryEventBus()
    await bus.start()
    logger.info("event bus: using in-process asyncio queue bus")
    return bus
