from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    factory = get_container(request).session_factory
    async with factory() as session:
        yield session
