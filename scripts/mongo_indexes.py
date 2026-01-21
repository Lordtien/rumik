from __future__ import annotations

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ira")


async def main() -> None:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]

    # users
    await db.users.create_index([("tier", 1), ("last_seen_at", -1)], name="tier_lastSeen")

    # personalities
    await db.personalities.create_index(
        [("user_id", 1), ("updated_at", -1)],
        name="user_updatedAt",
    )

    # sessions
    await db.sessions.create_index(
        [("user_id", 1), ("day", 1), ("status", 1)],
        name="user_day_status",
    )
    await db.sessions.create_index([("tier", 1), ("day", 1)], name="tier_day")

    # messages
    await db.messages.create_index(
        [("session_id", 1), ("created_at", -1)],
        name="session_createdAt_desc",
    )
    await db.messages.create_index([("tier", 1), ("created_at", -1)], name="tier_createdAt_desc")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())

