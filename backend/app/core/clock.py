"""Single clock for production and accelerated historical replay."""
from __future__ import annotations

import datetime as dt
import time
from app.core.time import utc_naive


class Clock:
    def __init__(self) -> None:
        self._virtual_start: dt.datetime | None = None
        self._wall_start = 0.0
        self._speed = 1.0

    def configure(self, start: dt.datetime, speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self._virtual_start = utc_naive(start)
        self._wall_start = time.monotonic()
        self._speed = speed

    def now(self) -> dt.datetime:
        if self._virtual_start is None:
            return dt.datetime.utcnow()
        return self._virtual_start + dt.timedelta(seconds=(time.monotonic() - self._wall_start) * self._speed)

    def pause(self) -> dt.datetime:
        """Keep the final replay frame available for dashboard inspection."""
        frozen = self.now()
        self._virtual_start = frozen
        self._wall_start = time.monotonic()
        self._speed = 0.0
        return frozen

    def resume_live(self) -> None:
        self._virtual_start = None
        self._speed = 1.0

    def real_seconds(self, virtual_seconds: float) -> float:
        return virtual_seconds / self._speed if self._virtual_start is not None and self._speed > 0 else virtual_seconds


clock = Clock()
