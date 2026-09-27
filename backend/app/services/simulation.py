"""Start and stop the CSV replay together with the NDTP emulator."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.core.config import settings

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


class SimulationError(Exception):
    pass


class SimulationController:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._started_at = 0.0

    def replay_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start_replay(self) -> bool:
        """Launch playback. A second click while the CSV is still loading does not restart it."""
        if self.replay_running() and time.monotonic() - self._started_at < 90:
            return False
        self.stop_replay()
        schedule, traffic = _dataset_paths()
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "scripts.replay_csv",
                "--schedule",
                str(schedule),
                "--traffic",
                str(traffic),
                "--backend",
                "http://127.0.0.1:8000",
                "--speed",
                str(settings.replay_speed),
                "--start-at",
                settings.replay_start_at,
                "--pause-at-end",
            ],
            cwd=_BACKEND_DIR,
            start_new_session=True,
        )
        self._started_at = time.monotonic()
        return True

    def stop_replay(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            _terminate(process)
        subprocess.run(["pkill", "-f", "scripts.replay_csv"], check=False)

    async def emulator_running(self) -> bool:
        try:
            config = await _emulator_request("GET")
        except httpx.HTTPError:
            return False
        units = config.get("units") if isinstance(config, dict) else None
        return bool(units)

    async def start_emulator(self) -> None:
        await _emulator_request("POST", _emulator_config())

    async def stop_emulator(self) -> None:
        config = _emulator_config()
        await _emulator_request(
            "POST",
            {
                "targetHost": config.get("targetHost", "host.docker.internal"),
                "targetPort": config.get("targetPort", 9201),
                "units": [],
            },
        )


controller = SimulationController()


def _dataset_paths() -> tuple[Path, Path]:
    schedule = _resolve_path(
        settings.replay_schedule_path,
        [
            Path("/dataset/train/schedule.csv"),
            Path.home() / "Downloads/dataset/train/schedule.csv",
            _REPO_ROOT / "dataset/train/schedule.csv",
        ],
    )
    traffic = _resolve_path(
        settings.replay_traffic_path,
        [
            Path("/dataset/train/traffic.csv"),
            Path.home() / "Downloads/dataset/train/traffic.csv",
            _REPO_ROOT / "dataset/train/traffic.csv",
        ],
    )
    if schedule is None or traffic is None:
        raise SimulationError("CSV расписания и телеметрии не найдены")
    return schedule, traffic


def _resolve_path(configured: str, candidates: list[Path]) -> Path | None:
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _emulator_config() -> dict:
    path = Path(settings.emulator_config_path) if settings.emulator_config_path else _REPO_ROOT / "emulator_sample_config.json"
    if not path.is_file():
        raise SimulationError(f"конфиг эмулятора не найден: {path}")
    return json.loads(path.read_text())


async def _emulator_request(method: str, payload: dict | None = None) -> dict:
    url = f"{settings.emulator_url.rstrip('/')}/api/config"
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.request(method, url, json=payload)
        response.raise_for_status()
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {}


def _terminate(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
