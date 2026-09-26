"""Large imports must stay below asyncpg's bind-parameter limit."""
import datetime as dt
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects.postgresql import asyncpg

from app.domain.entities import ScheduleStop
from app.repositories.schedule_repo import ScheduleRepository


@pytest.mark.asyncio
async def test_large_schedule_respects_postgres_parameter_limit():
    session = Mock()
    session.get_bind.return_value.dialect.name = 'postgresql'
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    stops = [ScheduleStop(tr_id=1, stop_id=i, seq=i, scheduled_time=dt.datetime(2026, 1, 6))
             for i in range(16674)]
    assert await ScheduleRepository(session).bulk_upsert(stops) == len(stops)
    saved_ids = []
    for call in session.execute.call_args_list:
        params = call.args[0].compile(dialect=asyncpg.dialect()).params
        assert len(params) <= 32767
        saved_ids.extend(v for k, v in params.items() if k.startswith('stop_id_'))
    assert sorted(saved_ids) == list(range(len(stops)))
    session.commit.assert_awaited_once()
