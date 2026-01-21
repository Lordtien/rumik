from __future__ import annotations

import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from services.common.logging import get_logger


log = get_logger("mongo")

_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        log.info("mongo_connect", extra={"extra": {"uri": uri}})
        _client = AsyncIOMotorClient(uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    name = os.getenv("MONGO_DB", "ira")
    return get_mongo_client()[name]


async def close_mongo() -> None:
    global _client
    if _client is not None:
        log.info("mongo_close")
        _client.close()
        _client = None

