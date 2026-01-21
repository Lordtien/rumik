from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from services.router.app.pools import PoolManager, PoolName, PoolOverloaded

Tier = Literal["free", "premium", "enterprise"]


@dataclass(frozen=True)
class RouteDecision:
    pool: PoolName | None
    action: Literal["forward", "shed"]
    reason: str
    user_message: str


class TierRouter:
    """Tier-aware routing policy with graceful degradation.

    Goals:
    - Enterprise remains stable: never displaced by lower tiers.
    - Premium degrades more slowly than free.
    - Free sheds gracefully (friendly response).
    """

    def __init__(self, pools: PoolManager) -> None:
        self.pools = pools

    def decide(self, tier: Tier) -> list[tuple[PoolName, float]]:
        """Return ordered candidate pools with max_queue_wait_s."""
        if tier == "enterprise":
            # Always try priority first; no queue wait in router (failover quickly).
            return [("priority", 0.0), ("overflow", 0.05)]
        if tier == "premium":
            # Try standard with small bounded wait; then overflow; then priority only if available.
            return [("standard", 0.10), ("overflow", 0.05), ("priority", 0.0)]
        # free
        return [("overflow", 0.0)]

    def shed_message(self, tier: Tier) -> str:
        if tier == "enterprise":
            return "I’m here—give me a moment while I catch up."
        if tier == "premium":
            return "I’m a bit busy right now—try again in a few seconds?"
        return "I’m getting a lot of messages right now—could you try again shortly?"

    async def route_and_call(
        self, *, tier: Tier, payload: dict[str, Any]
    ) -> tuple[RouteDecision, dict[str, Any] | None]:
        # Prefer healthy pools; but for enterprise we may still try even if health is stale.
        candidates = self.decide(tier)

        last_reason = "no_candidate"
        for pool, wait_s in candidates:
            st = self.pools.state[pool]
            if tier != "enterprise" and not st.healthy:
                last_reason = f"unhealthy:{pool}"
                continue

            try:
                resp = await self.pools.call_process(
                    pool=pool, payload=payload, max_queue_wait_s=wait_s
                )
                if resp.status_code == 200:
                    return (
                        RouteDecision(pool=pool, action="forward", reason="ok", user_message=""),
                        resp.json(),
                    )
                last_reason = f"bad_status:{pool}:{resp.status_code}"
            except PoolOverloaded:
                last_reason = f"overloaded:{pool}"
            except Exception as e:  # noqa: BLE001
                last_reason = f"error:{pool}:{type(e).__name__}"

        # Nothing worked -> graceful shed.
        return (
            RouteDecision(pool=None, action="shed", reason=last_reason, user_message=self.shed_message(tier)),
            None,
        )

