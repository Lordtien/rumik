from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from services.common.logging import get_logger
from services.common.analytics import start as analytics_start, stop as analytics_stop, track as analytics_track
from services.common.http import install_request_context_middleware
from services.common.request_context import RequestContext, get_request_context, set_request_context
from services.router.app.pools import PoolManager, load_pool_configs_from_env
from services.router.app.tier_router import Tier, TierRouter


log = get_logger("router")

pool_manager: PoolManager | None = None
tier_router: TierRouter | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool_manager, tier_router
    # Router owns the pool manager + http client.
    pool_manager = PoolManager(load_pool_configs_from_env())
    await analytics_start()
    await pool_manager.start_health_polling(interval_s=float(os.getenv("POOL_HEALTH_INTERVAL_S", "1.0")))
    tier_router = TierRouter(pool_manager)
    yield
    if pool_manager is not None:
        await pool_manager.aclose()
    await analytics_stop()


app = FastAPI(title="ira-router", lifespan=lifespan)
install_request_context_middleware(app, service="router")


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=8000)
    tier: str = Field("free", pattern="^(free|premium|enterprise)$")


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    started = time.perf_counter()

    # Update context with request-specific info (used by structured logs),
    # while preserving middleware-generated correlation ID.
    ctx = get_request_context()
    correlation_id = ctx.correlation_id if ctx is not None else "missing-correlation-id"
    set_request_context(
        RequestContext(
            correlation_id=correlation_id,
            service="router",
            user_id=req.user_id,
            tier=req.tier,
            operation="chat",
        )
    )

    assert tier_router is not None and pool_manager is not None

    payload = {"user_id": req.user_id, "message": req.message, "tier": req.tier}
    decision, result = await tier_router.route_and_call(tier=req.tier, payload=payload)  # type: ignore[arg-type]

    log.info(
        "routed",
        extra={
            "extra": {
                "user_id": req.user_id,
                "tier": req.tier,
                "action": decision.action,
                "pool": decision.pool,
                "reason": decision.reason,
            }
        },
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    # Fire-and-forget analytics (non-blocking enqueue).
    await analytics_track(
        {
            "ts": time.time(),
            "correlation_id": correlation_id,
            "user_id": req.user_id,
            "tier": req.tier,
            "pool": decision.pool,
            "latency_ms": round(elapsed_ms, 2),
            "rate_limited": bool((result or {}).get("rate_limited")),
            "safety_blocked": bool((result or {}).get("blocked")),
            "degraded": decision.action == "shed",
            "path": str(request.url.path),
        }
    )

    if decision.action == "shed":
        return {"reply": decision.user_message, "tier": req.tier, "degraded": True}

    return {
        "reply": (result or {}).get("reply", "OK"),
        "tier": req.tier,
        "pool": decision.pool,
        "degraded": False,
        "rate_limited": bool((result or {}).get("rate_limited")),
        "silent": bool((result or {}).get("silent")),
        "blocked": bool((result or {}).get("blocked")),
    }


@app.get("/pools")
async def pools():
    assert pool_manager is not None
    return pool_manager.snapshot()


