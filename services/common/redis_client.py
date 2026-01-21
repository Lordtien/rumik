from __future__ import annotations

import os

import redis.asyncio as redis

from services.common.logging import get_logger


log = get_logger("redis")

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        log.info("redis_connect", extra={"extra": {"url": url}})
        _client = redis.from_url(url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        log.info("redis_close")
        await _client.aclose()
        _client = None

