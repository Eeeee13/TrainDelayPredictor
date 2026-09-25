from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.container import Container

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/risk")
async def ws_risk(ws: WebSocket) -> None:
    container: Container = ws.app.state.container
    await container.ws_hub.connect(ws, container.state_cache.all_risk())
    try:
        while True:
            # dashboard doesn't need to send anything; just keep the
            # connection alive and detect disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await container.ws_hub.disconnect(ws)
