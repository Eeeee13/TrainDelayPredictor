from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from pathlib import Path

from app.core.config import settings
from app.db.base import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=settings.db_echo, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _session_factory


async def init_db() -> None:
    """Create tables if missing. A hackathon-speed substitute for Alembic
    migrations — fine for a from-scratch competition deployment; swap for
    `alembic upgrade head` if this ever needs real schema evolution.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql":
            migration = Path(__file__).resolve().parents[2] / "migrations/001_ml_columns.sql"
            for statement in migration.read_text().split(";"):
                if not statement.strip():
                    continue
                await conn.execute(text(statement))
            await conn.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'inference_ro') THEN CREATE ROLE inference_ro LOGIN PASSWORD 'inference_ro'; END IF; END $$"))
            await conn.execute(text("GRANT CONNECT ON DATABASE predictor TO inference_ro"))
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO inference_ro"))
            await conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO inference_ro"))


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
