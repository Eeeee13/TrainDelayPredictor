from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, ingestion, predictions, vehicles, websocket
from app.core.config import settings
from app.core.container import build_container
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("starting %s", settings.app_name)

    await init_db()
    container = await build_container()
    app.state.container = container

    tasks = [
        asyncio.create_task(container.telemetry_worker.run_forever(), name="telemetry-worker"),
        asyncio.create_task(container.scheduler.run_forever(), name="prediction-scheduler"),
    ]

    try:
        yield
    finally:
        container.scheduler.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await container.event_bus.stop()
        await dispose_engine()
        logger.info("shutdown complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingestion.router)
app.include_router(vehicles.router)
app.include_router(predictions.router)
app.include_router(websocket.router)
