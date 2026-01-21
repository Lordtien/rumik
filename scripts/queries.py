from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ira")


def utc_day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


async def _explain_aggregate(
    db: AsyncIOMotorDatabase,
    *,
    collection: str,
    pipeline: list[dict],
) -> dict:
    """Use MongoDB's explain command with executionStats verbosity."""
    cmd = {
        "explain": {
            "aggregate": collection,
            "pipeline": pipeline,
            "cursor": {},
        },
        "verbosity": "executionStats",
    }
    return await db.command(cmd)


async def explain_active_session_for_user(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    day = utc_day_key()
    pipeline = [
        {"$match": {"_id": user_id}},
        {
            "$lookup": {
                "from": "sessions",
                "let": {"uid": "$_id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$user_id", "$$uid"]},
                                    {"$eq": ["$day", day]},
                                    {"$eq": ["$status", "active"]},
                                ]
                            }
                        }
                    },
                    {"$sort": {"started_at": -1}},
                    {"$limit": 1},
                    {"$project": {"_id": 1, "day": 1, "status": 1, "last_activity_at": 1}},
                ],
                "as": "active_session",
            }
        },
        {"$project": {"_id": 1, "tier": 1, "active_session": 1}},
    ]
    return await _explain_aggregate(db, collection="users", pipeline=pipeline)


async def explain_recent_messages_for_session(
    db: AsyncIOMotorDatabase, session_id: str, limit_n: int = 20
) -> dict:
    # Use sessions as the anchor to demonstrate $lookup for "context fetch".
    pipeline = [
        {"$match": {"_id": session_id}},
        {
            "$lookup": {
                "from": "messages",
                "let": {"sid": "$_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$session_id", "$$sid"]}}},
                    {"$sort": {"created_at": -1}},
                    {"$limit": int(limit_n)},
                    {"$project": {"_id": 1, "role": 1, "content": 1, "created_at": 1}},
                ],
                "as": "recent_messages",
            }
        },
        {"$project": {"_id": 1, "user_id": 1, "day": 1, "recent_messages": 1}},
    ]
    return await _explain_aggregate(db, collection="sessions", pipeline=pipeline)


async def explain_agg_by_tier_activity(db: AsyncIOMotorDatabase) -> dict:
    # Example aggregation: sessions per tier for today.
    day = utc_day_key()
    pipeline = [
        {"$match": {"day": day}},
        {"$group": {"_id": "$tier", "sessions": {"$sum": 1}, "msgs": {"$sum": "$message_count"}}},
        {"$sort": {"sessions": -1}},
    ]
    return await _explain_aggregate(db, collection="sessions", pipeline=pipeline)


async def main() -> None:
    user_id = os.getenv("EXPLAIN_USER_ID", "")
    session_id = os.getenv("EXPLAIN_SESSION_ID", "")

    if not user_id or not session_id:
        raise SystemExit(
            "Set EXPLAIN_USER_ID and EXPLAIN_SESSION_ID env vars to run explains."
        )

    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]

    print("\n=== explain: active session for user ($lookup) ===")
    print(await explain_active_session_for_user(db, user_id))

    print("\n=== explain: recent messages for session ($lookup) ===")
    print(await explain_recent_messages_for_session(db, session_id, limit_n=20))

    print("\n=== explain: aggregation by tier/activity ===")
    print(await explain_agg_by_tier_activity(db))

    client.close()


if __name__ == "__main__":
    asyncio.run(main())

