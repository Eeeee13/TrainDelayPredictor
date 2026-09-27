"""Minimal NDTP TCP receiver for the emulator's navigation cell."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import struct

from app.bus.event_bus import TOPIC_TELEMETRY, EventBus

logger = logging.getLogger(__name__)
NAV = struct.Struct("<IIIBBHHHHHBB")
CELL_SIZES = {0: 26, 2: 26, 8: 6, 10: 37, 15: 50, 16: 8}
REDIS_KEY = "ndtp_unit_map"


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def decode_frame(npl: bytes, body: bytes, unit_map: dict[str, int]) -> dict | None:
    if len(npl) != 15 or npl[:2] != b"~~" or npl[8] != 2:
        return None
    if npl[6:8] != crc16(body).to_bytes(2, "big"):
        raise ValueError("NDTP CRC mismatch")
    service, kind = struct.unpack_from("<HH", body)
    if (service, kind) != (1, 101) or len(body) < 10 + 2 + NAV.size:
        return None
    cell_type, _ = body[10:12]
    if cell_type != 0:
        return None
    (timestamp, lon, lat, flags, _battery, speed, _max_speed,
     _course, _track, _alt, _nsat, _pdop) = NAV.unpack_from(body, 12)
    unit_id = struct.unpack_from("<I", npl, 9)[0]
    tr_id = unit_map.get(str(unit_id))
    if tr_id is None:
        logger.warning("unmapped NDTP unit_id=%s", unit_id)
        return None
    valid = bool(flags & 0x80)
    return {
        "vehicle_id": str(tr_id), "tr_id": tr_id,
        "event_time": dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).replace(tzinfo=None).isoformat(),
        "longitude": lon / 1e7 * (1 if flags & 0x40 else -1),
        "latitude": lat / 1e7 * (1 if flags & 0x20 else -1),
        "speed": float(speed), "location_valid": valid, "door_open": False,
    }


async def serve(event_bus: EventBus, redis, host: str = "0.0.0.0", port: int = 9201) -> asyncio.AbstractServer:
    """Load unit_map from Redis with ENV fallback."""
    unit_map = {str(k): int(v) for k, v in json.loads(os.getenv("APP_NDTP_UNIT_MAP", "{}")).items()}
    try:
        mapping_json = await redis.get(REDIS_KEY)
        if mapping_json:
            unit_map.update({str(k): int(v) for k, v in json.loads(mapping_json).items()})
            logger.info("Loaded %d NDTP mappings from Redis", len(unit_map))
    except Exception as e:
        logger.warning("Failed to load NDTP mapping from Redis: %s", e)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                npl = await reader.readexactly(15)
                if npl[:2] != b"~~":
                    raise ValueError("invalid NDTP signature")
                size = struct.unpack_from("<H", npl, 2)[0]
                if not 10 <= size <= 65535:
                    raise ValueError("invalid NDTP frame size")
                body = await reader.readexactly(size)
                try:
                    payload = decode_frame(npl, body, unit_map)
                    if payload:
                        await event_bus.publish(TOPIC_TELEMETRY, payload)
                except ValueError:
                    logger.warning("discarding NDTP frame with bad CRC")
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception:
            logger.exception("NDTP connection failed")
        finally:
            writer.close()
            await writer.wait_closed()

    return await asyncio.start_server(handle, host, port)
