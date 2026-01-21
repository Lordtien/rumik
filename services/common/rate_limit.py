from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from services.common.redis_client import get_redis


Tier = Literal["free", "premium", "enterprise"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_day_key(now: Optional[datetime] = None) -> str:
    now = now or _utc_now()
    return now.strftime("%Y-%m-%d")


def _seconds_until_utc_midnight(now: Optional[datetime] = None) -> int:
    now = now or _utc_now()
    tomorrow = (now + timedelta(days=1)).date()
    midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc)
    return max(1, int((midnight - now).total_seconds()))


def _limit_for_tier(tier: Tier) -> Optional[int]:
    if tier == "enterprise":
        return None
    if tier == "premium":
        return 100
    return 10


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: Optional[int]
    reset_in_seconds: int
    first_notice: bool


class SessionDayLimiter:
    """Per-user per-day (session) message limiter with 'first notice then silent' behavior.

    Keys:
    - count key: counts messages for the day
    - notice key: records that we already sent the friendly limit message for the day
    """

    def __init__(self, *, namespace: str = "ira") -> None:
        self.ns = namespace

    def _count_key(self, user_id: str, day: str) -> str:
        return f"{self.ns}:rl:count:{day}:{user_id}"

    def _notice_key(self, user_id: str, day: str) -> str:
        return f"{self.ns}:rl:notice:{day}:{user_id}"

    async def check_and_increment(self, *, user_id: str, tier: Tier) -> RateLimitResult:
        limit = _limit_for_tier(tier)
        reset_in = _seconds_until_utc_midnight()
        day = _utc_day_key()

        if limit is None:
            return RateLimitResult(allowed=True, remaining=None, reset_in_seconds=reset_in, first_notice=False)

        r = get_redis()
        count_key = self._count_key(user_id, day)
        notice_key = self._notice_key(user_id, day)

        # Increment first, then evaluate. Set expiries to midnight.
        pipe = r.pipeline()
        pipe.incr(count_key)
        pipe.ttl(count_key)
        res = await pipe.execute()
        count = int(res[0])
        ttl = int(res[1])

        # If ttl wasn't set yet, set it.
        if ttl < 0:
            await r.expire(count_key, reset_in)

        remaining = max(0, limit - count)
        allowed = count <= limit

        if allowed:
            return RateLimitResult(allowed=True, remaining=remaining, reset_in_seconds=reset_in, first_notice=False)

        # Over limit: check whether we've already sent a notice today.
        # Use SET NX with expiry to avoid repeated messages.
        first_notice = await r.set(notice_key, "1", ex=reset_in, nx=True)
        return RateLimitResult(
            allowed=False,
            remaining=0,
            reset_in_seconds=reset_in,
            first_notice=bool(first_notice),
        )


def human_reset_message(reset_in_seconds: int) -> str:
    # We keep it simple and human-sounding.
    hours = max(1, int(math.ceil(reset_in_seconds / 3600)))
    if hours == 1:
        return "I need a bit of rest—text me again in about an hour."
    return f"I need to rest a little—text me again in about {hours} hours."

