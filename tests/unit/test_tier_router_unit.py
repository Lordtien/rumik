from __future__ import annotations

from typing import Any

import pytest

from services.router.app.tier_router import TierRouter


class FakePools:
    def __init__(self) -> None:
        # mimic PoolManager.state shape
        self.state = {
            "priority": type("S", (), {"healthy": True})(),
            "standard": type("S", (), {"healthy": True})(),
            "overflow": type("S", (), {"healthy": True})(),
        }
        self.calls: list[str] = []

    async def call_process(self, *, pool: str, payload: dict[str, Any], max_queue_wait_s: float = 0.0):
        self.calls.append(pool)
        # Simulate overflow success, others fail depending on test.
        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"reply": f"ok:{pool}"}

        return R()


@pytest.mark.asyncio
async def test_free_routes_to_overflow_only():
    pools = FakePools()
    router = TierRouter(pools)  # type: ignore[arg-type]

    decision, result = await router.route_and_call(tier="free", payload={"x": 1})
    assert decision.action == "forward"
    assert decision.pool == "overflow"
    assert pools.calls == ["overflow"]
    assert result and result["reply"] == "ok:overflow"


@pytest.mark.asyncio
async def test_premium_skips_unhealthy_standard_and_falls_back_to_overflow():
    pools = FakePools()
    pools.state["standard"].healthy = False
    router = TierRouter(pools)  # type: ignore[arg-type]

    decision, _ = await router.route_and_call(tier="premium", payload={"x": 1})
    assert decision.action == "forward"
    assert decision.pool == "overflow"
    assert pools.calls[0] == "overflow"


@pytest.mark.asyncio
async def test_shed_when_all_candidates_unhealthy(monkeypatch: pytest.MonkeyPatch):
    pools = FakePools()
    pools.state["overflow"].healthy = False

    async def fail_call_process(*args: Any, **kwargs: Any):
        raise RuntimeError("boom")

    monkeypatch.setattr(pools, "call_process", fail_call_process)
    router = TierRouter(pools)  # type: ignore[arg-type]

    decision, result = await router.route_and_call(tier="free", payload={"x": 1})
    assert decision.action == "shed"
    assert result is None
    assert isinstance(decision.user_message, str) and decision.user_message

