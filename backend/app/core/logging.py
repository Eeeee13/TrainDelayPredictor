"""Structured-ish logging setup. Kept deliberately simple (stdlib logging,
JSON-free) — the observability requirement here is "every prediction and
degradation event is traceable in logs", not a full metrics stack.
"""
from __future__ import annotations

import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # idempotent - avoid duplicate handlers on reload
    root.setLevel(settings.log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    # noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
