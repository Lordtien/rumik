from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from services.common.mongo import get_db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_day_key(dt: Optional[datetime] = None) -> str:
    dt = dt or _utc_now()
    return dt.strftime("%Y-%m-%d")


class UsersRepo:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db or get_db()
        self._col: AsyncIOMotorCollection = self._db.users

    async def get_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        return await self._col.find_one({"_id": user_id})


class PersonalitiesRepo:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db or get_db()
        self._col: AsyncIOMotorCollection = self._db.personalities

    async def get_latest_for_user(self, user_id: str) -> Optional[dict[str, Any]]:
        doc = await self._col.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1)],
        )
        return doc


class SessionsRepo:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db or get_db()
        self._col: AsyncIOMotorCollection = self._db.sessions

    async def get_active_for_user_today(self, user_id: str) -> Optional[dict[str, Any]]:
        """Hot-path query 1: fetch current active session for a user (calendar-day)."""
        day = _utc_day_key()
        return await self._col.find_one(
            {"user_id": user_id, "day": day, "status": "active"},
            sort=[("started_at", -1)],
            projection={"_id": 1, "user_id": 1, "day": 1, "status": 1, "last_activity_at": 1},
        )


class MessagesRepo:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db = db or get_db()
        self._col: AsyncIOMotorCollection = self._db.messages

    async def get_recent_for_session(self, session_id: str, limit_n: int = 20) -> list[dict[str, Any]]:
        """Hot-path query 2: recent N messages for contextual LLM calls."""
        cursor = self._col.find(
            {"session_id": session_id},
            projection={"_id": 1, "role": 1, "content": 1, "created_at": 1},
            sort=[("created_at", -1)],
            limit=limit_n,
        )
        return [doc async for doc in cursor]

