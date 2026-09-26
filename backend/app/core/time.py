"""Normalize API timestamps to naive UTC for the existing database schema."""
from __future__ import annotations

import datetime as dt


def utc_naive(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
