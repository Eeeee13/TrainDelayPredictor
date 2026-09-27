"""Centralized configuration. Every tunable that affects correctness
(horizon window, thresholds, timeouts) lives here — nothing is a magic
number buried in a service.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    # --- Database -----------------------------------------------------
    # Async Postgres DSN (asyncpg driver). Tests override this with an
    # in-memory sqlite+aiosqlite DSN — see tests/conftest.py.
    database_url: str = "postgresql+asyncpg://predictor:predictor@localhost:5432/predictor"
    db_echo: bool = False

    # --- Event bus ------------------------------------------------------
    # Two topics of interest end-to-end: telemetry -> features (internal,
    # observability) -> predictions -> alerts. Backed by Redis Streams when
    # available (architecturally decoupled Backend <-> ML), otherwise an
    # in-process asyncio.Queue bus so the service still runs standalone.
    redis_url: str | None = "redis://redis:6379/0"
    use_redis_streams: bool = True

    # --- ML inference ---------------------------------------------------
    inference_url: str = "http://inference:8000/predict"
    inference_timeout_s: float = 2.0
    inference_max_retries: int = 1
    inference_circuit_cooldown_s: float = 15.0
    inference_circuit_fail_threshold: int = 3

    # --- Forecast horizon (hard requirement: strictly 10-15 minutes) ----
    horizon_min_s: int = 600   # 10 min - closest allowed lead time
    horizon_max_s: int = 900   # 15 min - earliest allowed lead time (fire point)
    # --- Scheduling -------------------------------------------------
    scheduler_tick_s: float = 5.0
    safety_recompute_interval_s: float = 60.0
    schedule_lookahead_s: int = 3600  # how far ahead to keep stops "live" in the calendar
    stale_vehicle_after_s: int = 180  # drop a vehicle from the live calendar if silent this long

    # --- Risk thresholds (seconds of predicted delay) --------------------
    risk_threshold_medium_s: int = 120
    risk_threshold_high_s: int = 300

    # --- Matching engine --------------------------------------------------
    stop_match_radius_m: float = 60.0

    # --- Misc ---------------------------------------------------------
    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"
    app_name: str = "predictor-backend"


settings = Settings()
