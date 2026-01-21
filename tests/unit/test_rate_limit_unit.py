from __future__ import annotations

import pytest

from services.common import rate_limit as rl
from tests.unit.fake_redis import FakeRedis


@pytest.mark.asyncio
async def test_session_day_limiter_first_notice_then_silent(monkeypatch: pytest.MonkeyPatch):
    fake = FakeRedis()
    monkeypatch.setattr(rl, "get_redis", lambda: fake)
    # Make reset deterministic for test; keep ttl large enough.
    monkeypatch.setattr(rl, "_seconds_until_utc_midnight", lambda now=None: 3600)
    monkeypatch.setattr(rl, "_utc_day_key", lambda now=None: "2099-01-01")

    limiter = rl.SessionDayLimiter(namespace="test")

    # free limit=10, so first 10 allowed
    for i in range(10):
        res = await limiter.check_and_increment(user_id="u1", tier="free")
        assert res.allowed is True
        assert res.first_notice is False

    # 11th is over limit -> first notice
    res = await limiter.check_and_increment(user_id="u1", tier="free")
    assert res.allowed is False
    assert res.first_notice is True
    assert res.reset_in_seconds == 3600

    # 12th -> silent (no notice)
    res = await limiter.check_and_increment(user_id="u1", tier="free")
    assert res.allowed is False
    assert res.first_notice is False


@pytest.mark.asyncio
async def test_enterprise_unlimited(monkeypatch: pytest.MonkeyPatch):
    fake = FakeRedis()
    monkeypatch.setattr(rl, "get_redis", lambda: fake)
    monkeypatch.setattr(rl, "_seconds_until_utc_midnight", lambda now=None: 3600)
    monkeypatch.setattr(rl, "_utc_day_key", lambda now=None: "2099-01-01")

    limiter = rl.SessionDayLimiter(namespace="test")
    for _ in range(1000):
        res = await limiter.check_and_increment(user_id="ent", tier="enterprise")
        assert res.allowed is True
        assert res.remaining is None


def test_human_reset_message_is_non_technical():
    msg = rl.human_reset_message(8 * 3600)
    assert isinstance(msg, str)
    assert "rate" not in msg.lower()
    assert "limit" not in msg.lower()
    assert "quota" not in msg.lower()

