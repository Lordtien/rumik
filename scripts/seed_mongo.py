from __future__ import annotations

import asyncio
import os
import random
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from motor.motor_asyncio import AsyncIOMotorClient


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ira")

# Target sizes (default to 1M each; override locally for smaller runs)
N_USERS = int(os.getenv("SEED_USERS", "1000000"))
N_PERSONALITIES = int(os.getenv("SEED_PERSONALITIES", str(N_USERS)))
N_SESSIONS = int(os.getenv("SEED_SESSIONS", "1000000"))
N_MESSAGES = int(os.getenv("SEED_MESSAGES", "1000000"))

BATCH_SIZE = int(os.getenv("SEED_BATCH_SIZE", "2000"))
CONCURRENCY = int(os.getenv("SEED_CONCURRENCY", "8"))

DAY_SPAN = int(os.getenv("SEED_DAY_SPAN", "30"))  # sessions spread across last N days

DROP_DB = os.getenv("SEED_DROP_DB", "false").lower() in {"1", "true", "yes"}


TIERS = ("free", "premium", "enterprise")
TIER_WEIGHTS = (0.90, 0.09, 0.01)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def rand_text(min_len: int = 20, max_len: int = 220) -> str:
    # Fast, dependency-free pseudo-natural text.
    words = [
        "hey",
        "ira",
        "today",
        "feel",
        "like",
        "need",
        "help",
        "plan",
        "work",
        "focus",
        "stress",
        "sleep",
        "schedule",
        "ideas",
        "quick",
        "question",
        "thanks",
        "understand",
        "explain",
        "steps",
    ]
    target = random.randint(min_len, max_len)
    out: list[str] = []
    total = 0
    while total < target:
        w = random.choice(words)
        out.append(w)
        total += len(w) + 1
    s = " ".join(out)[:target].strip()
    # Add a tiny bit of punctuation variety.
    if random.random() < 0.2:
        s += random.choice([".", "?", "!"])
    return s


def sample_tier() -> str:
    return random.choices(TIERS, weights=TIER_WEIGHTS, k=1)[0]


def uuid_str() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class SeedIds:
    user_ids: list[str]
    session_ids: list[str]


async def _insert_many(db, collection: str, docs: list[dict]) -> None:
    if not docs:
        return
    await db[collection].insert_many(docs, ordered=False)


def _chunks(it: Iterable, size: int):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


async def seed_users(db) -> list[str]:
    now = utc_now()
    user_ids: list[str] = []

    sem = asyncio.Semaphore(CONCURRENCY)

    async def worker(batch_docs: list[dict]) -> None:
        async with sem:
            await _insert_many(db, "users", batch_docs)

    tasks: list[asyncio.Task] = []
    batch: list[dict] = []

    for _ in range(N_USERS):
        uid = uuid_str()
        user_ids.append(uid)
        tier = sample_tier()
        created_at = now - timedelta(days=random.randint(0, 365))
        last_seen_at = now - timedelta(minutes=random.randint(0, 60 * 24 * 30))
        batch.append(
            {
                "_id": uid,
                "tier": tier,
                "created_at": created_at,
                "status": "active",
                "active_session_key": None,  # populated after sessions are generated
                "last_seen_at": last_seen_at,
                "limits": {"tier": tier},
            }
        )
        if len(batch) >= BATCH_SIZE:
            tasks.append(asyncio.create_task(worker(batch)))
            batch = []

    if batch:
        tasks.append(asyncio.create_task(worker(batch)))

    await asyncio.gather(*tasks)
    return user_ids


async def seed_personalities(db, user_ids: list[str]) -> None:
    now = utc_now()
    sem = asyncio.Semaphore(CONCURRENCY)

    tones = ["warm", "playful", "direct"]
    style_snippets = [
        "Keep replies concise and friendly.",
        "Ask one clarifying question if needed.",
        "Avoid harsh system-sounding language.",
    ]

    async def worker(batch_docs: list[dict]) -> None:
        async with sem:
            await _insert_many(db, "personalities", batch_docs)

    tasks: list[asyncio.Task] = []
    batch: list[dict] = []

    # One personality per user (default)
    for uid in user_ids[:N_PERSONALITIES]:
        pid = uuid_str()
        batch.append(
            {
                "_id": pid,
                "user_id": uid,
                "version": 1,
                "tone": random.choice(tones),
                "style_prompts": random.sample(style_snippets, k=random.randint(1, len(style_snippets))),
                "safety_voice": {
                    "refuse_soft": "I can’t help with that, but I can help with something safer if you want.",
                },
                "updated_at": now - timedelta(days=random.randint(0, 120)),
            }
        )
        if len(batch) >= BATCH_SIZE:
            tasks.append(asyncio.create_task(worker(batch)))
            batch = []

    if batch:
        tasks.append(asyncio.create_task(worker(batch)))

    await asyncio.gather(*tasks)


async def seed_sessions(db, user_ids: list[str]) -> list[str]:
    now = utc_now()
    sem = asyncio.Semaphore(CONCURRENCY)

    # Long-tail activity: a small cohort will have “today” sessions and higher message_count.
    # We still cap total sessions to N_SESSIONS.
    session_ids: list[str] = []

    async def worker(batch_docs: list[dict]) -> None:
        async with sem:
            await _insert_many(db, "sessions", batch_docs)

    tasks: list[asyncio.Task] = []
    batch: list[dict] = []

    # Choose users that will get a "today" session (approx 10%).
    today = now
    today_users = set(random.sample(user_ids, k=max(1, int(0.10 * len(user_ids)))))

    # Generate sessions by sampling users without replacement where possible.
    chosen_users = random.sample(user_ids, k=min(N_SESSIONS, len(user_ids)))

    for uid in chosen_users:
        sid = uuid_str()
        session_ids.append(sid)

        # Spread across last DAY_SPAN days; ensure some are today.
        if uid in today_users:
            day_dt = today
        else:
            day_dt = now - timedelta(days=random.randint(0, max(0, DAY_SPAN - 1)))

        started_at = day_dt.replace(hour=random.randint(0, 23), minute=random.randint(0, 59))
        last_activity_at = started_at + timedelta(minutes=random.randint(0, 8 * 60))

        # Message count skewed: most small, some large.
        if uid in today_users and random.random() < 0.3:
            msg_count = random.randint(30, 200)
        else:
            msg_count = max(1, int(random.paretovariate(2.0)))  # typically 1–5

        # Read tier from users collection is expensive here; so we approximate via distribution
        # and later denormalize from user docs during real pipeline. For seeding we keep it simple.
        tier = sample_tier()

        batch.append(
            {
                "_id": sid,
                "user_id": uid,
                "day": day_key(day_dt),
                "status": "active" if day_key(day_dt) == day_key(now) else "closed",
                "started_at": started_at,
                "last_activity_at": last_activity_at,
                "message_count": msg_count,
                "tier": tier,
            }
        )

        if len(batch) >= BATCH_SIZE:
            tasks.append(asyncio.create_task(worker(batch)))
            batch = []

    if batch:
        tasks.append(asyncio.create_task(worker(batch)))

    await asyncio.gather(*tasks)

    # Denormalize active_session_key on users for users that have today's session.
    # We do this as a bulk best-effort update to support fast "active session" lookups later.
    # active_session_key = f"{day}:{session_id}"
    today_key = day_key(now)
    cursor = db.sessions.find({"day": today_key}, {"_id": 1, "user_id": 1})
    ops = []
    async for doc in cursor:
        ops.append(
            (
                doc["user_id"],
                f"{today_key}:{doc['_id']}",
            )
        )
        if len(ops) >= 5000:
            await _bulk_set_active_session_key(db, ops)
            ops = []
    if ops:
        await _bulk_set_active_session_key(db, ops)

    return session_ids


async def _bulk_set_active_session_key(db, pairs: list[tuple[str, str]]) -> None:
    # Avoid importing pymongo UpdateOne in hot path unless needed; motor exposes pymongo.
    from pymongo import UpdateOne

    ops = [UpdateOne({"_id": uid}, {"$set": {"active_session_key": key}}) for uid, key in pairs]
    if ops:
        await db.users.bulk_write(ops, ordered=False)


async def seed_messages(db, session_ids: list[str]) -> None:
    now = utc_now()
    sem = asyncio.Semaphore(CONCURRENCY)

    # Skew: pick a subset of sessions as "hot" for message-heavy distribution.
    hot_sessions = set(random.sample(session_ids, k=max(1, int(0.05 * len(session_ids)))))

    async def worker(batch_docs: list[dict]) -> None:
        async with sem:
            await _insert_many(db, "messages", batch_docs)

    tasks: list[asyncio.Task] = []
    batch: list[dict] = []

    roles = ["user", "assistant"]
    for _ in range(N_MESSAGES):
        mid = uuid_str()
        sid = random.choice(session_ids if random.random() > 0.35 else list(hot_sessions))

        # We avoid a join here for speed; user_id and tier are best-effort seeded.
        # Real pipeline will set correct denormalized tier/user_id.
        tier = sample_tier()

        created_at = now - timedelta(minutes=random.randint(0, 60 * 24 * DAY_SPAN))
        batch.append(
            {
                "_id": mid,
                "user_id": None,
                "session_id": sid,
                "role": random.choice(roles),
                "content": rand_text(),
                "created_at": created_at,
                "tier": tier,
                "safety": {"blocked": False},
            }
        )

        if len(batch) >= BATCH_SIZE:
            tasks.append(asyncio.create_task(worker(batch)))
            batch = []

    if batch:
        tasks.append(asyncio.create_task(worker(batch)))

    await asyncio.gather(*tasks)


async def main() -> None:
    random.seed(int(os.getenv("SEED_RANDOM_SEED", "1337")))

    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]

    if DROP_DB:
        await client.drop_database(MONGO_DB)

    # Ensure collections exist early (Mongo creates on first insert anyway).
    print(f"Seeding db={MONGO_DB} uri={MONGO_URI}")
    print(
        f"Targets: users={N_USERS} personalities={N_PERSONALITIES} sessions={N_SESSIONS} messages={N_MESSAGES} "
        f"batch={BATCH_SIZE} conc={CONCURRENCY}"
    )

    user_ids = await seed_users(db)
    await seed_personalities(db, user_ids)
    session_ids = await seed_sessions(db, user_ids)
    await seed_messages(db, session_ids)

    client.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

