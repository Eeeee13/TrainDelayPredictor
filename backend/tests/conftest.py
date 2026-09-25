"""Tests run against an isolated in-memory SQLite DB (async, via
aiosqlite) with the in-process event bus and no external inference
service, so the whole suite runs with zero infra (no Docker, no Postgres,
no Redis) — the same reasoning the original hackathon prototype used.
Production always talks to real Postgres + (optionally) Redis Streams; only
the DSN/bus selection differs, the code under test is identical.
"""
from __future__ import annotations

import os

# Must happen before `app.core.config` (and anything importing it) loads.
os.environ["APP_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_USE_REDIS_STREAMS"] = "false"
os.environ["APP_INFERENCE_URL"] = "http://127.0.0.1:1/predict"  # unroutable -> fast connection failure -> fallback
os.environ["APP_INFERENCE_TIMEOUT_S"] = "0.3"
os.environ["APP_SCHEDULER_TICK_S"] = "0.2"
os.environ["APP_SAFETY_RECOMPUTE_INTERVAL_S"] = "1"

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base


@pytest_asyncio.fixture
async def sqlite_session_factory():
    """A fresh in-memory sqlite DB per test, schema created from the same
    ORM models used against Postgres in production.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()
