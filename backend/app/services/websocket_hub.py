from __future__ import annotations

import asyncio

from fastapi import WebSocket

from app.core.logging import get_logger
from app.domain.entities import RiskAssessment

logger = get_logger(__name__)


class WebSocketHub:
    """Fan-out of live RiskAssessment updates to every connected dashboard.
    A new connection gets today's full snapshot first, then a delta stream
    - no polling needed on the frontend side.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, snapshot: list[RiskAssessment]) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        await ws.send_json({"type": "snapshot", "items": [r.to_dict() for r in snapshot]})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, assessment: RiskAssessment) -> None:
        message = {"type": "update", "item": assessment.to_dict()}
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - a broken socket shouldn't break the broadcast loop
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
