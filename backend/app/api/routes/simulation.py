"""Dashboard controls for the historical replay and the NDTP emulator."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException

from app.core.clock import clock
from app.core.config import settings
from app.services.simulation import SimulationError, controller

router = APIRouter(prefix="/simulation", tags=["simulation"])


async def _status() -> dict:
    return {
        "replay": controller.replay_running(),
        "emulator": await controller.emulator_running(),
        "start_at": settings.replay_start_at,
    }


@router.get("")
async def simulation_status() -> dict:
    return await _status()


def _hold_at_replay_start() -> None:
    """Show 06:00 immediately. Playback speed starts when the CSV loader posts the clock."""
    start = dt.datetime.fromisoformat(settings.replay_start_at)
    if start.tzinfo is None:
        start = start.replace(tzinfo=ZoneInfo("Europe/Moscow"))
    clock.configure(start, settings.replay_speed)
    clock.pause()


@router.post("/start")
async def start_simulation() -> dict:
    errors: list[str] = []
    try:
        if controller.start_replay():
            _hold_at_replay_start()
    except SimulationError as exc:
        errors.append(str(exc))
    try:
        await controller.start_emulator()
    except SimulationError as exc:
        errors.append(str(exc))
    except httpx.HTTPError:
        errors.append("эмулятор недоступен")
    status = await _status()
    status["errors"] = errors
    if errors and not status["replay"] and not status["emulator"]:
        raise HTTPException(status_code=503, detail="; ".join(errors))
    return status


@router.post("/stop")
async def stop_simulation() -> dict:
    controller.stop_replay()
    clock.pause()
    errors: list[str] = []
    try:
        await controller.stop_emulator()
    except SimulationError as exc:
        errors.append(str(exc))
    except httpx.HTTPError:
        errors.append("эмулятор недоступен")
    status = await _status()
    status["errors"] = errors
    if errors and status["emulator"]:
        raise HTTPException(status_code=503, detail="; ".join(errors))
    return status
