"""NDTP unit_id to tr_id mapping management."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.core.container import Container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ndtp-mapping", tags=["ndtp-mapping"])
REDIS_KEY = "ndtp_unit_map"


@router.get("")
async def get_mapping(container: Container = Depends(get_container)) -> dict[str, Any]:
    """Get current NDTP unit_id to tr_id mapping."""
    redis = container.redis
    mapping_json = await redis.get(REDIS_KEY)
    if mapping_json is None:
        return {"mapping": {}}
    import json
    return {"mapping": json.loads(mapping_json)}


@router.post("")
async def set_mapping(
    mapping: dict[str, int],
    container: Container = Depends(get_container)
) -> dict[str, Any]:
    """Set NDTP unit_id to tr_id mapping."""
    import json
    redis = container.redis
    mapping_json = json.dumps(mapping)
    await redis.set(REDIS_KEY, mapping_json)
    logger.info("Updated NDTP mapping: %d entries", len(mapping))
    return {"mapping": mapping, "status": "updated"}


@router.delete("")
async def clear_mapping(container: Container = Depends(get_container)) -> dict[str, Any]:
    """Clear NDTP unit_id to tr_id mapping."""
    redis = container.redis
    await redis.delete(REDIS_KEY)
    logger.info("Cleared NDTP mapping")
    return {"status": "cleared"}
