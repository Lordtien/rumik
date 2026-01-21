from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel, Field

from services.common.app_factory import create_app
from services.common.logging import get_logger
from services.common.request_context import RequestContext, get_request_context, set_request_context
from services.common.rate_limit import SessionDayLimiter, human_reset_message
from services.common.safety import detect_unsafe, refusal_message


app = create_app(service="worker-overflow")
log = get_logger("worker-overflow")
limiter = SessionDayLimiter()


class ProcessRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=8000)
    tier: str = Field(..., pattern="^(free|premium|enterprise)$")


@app.post("/process")
async def process(req: ProcessRequest):
    ctx = get_request_context()
    correlation_id = ctx.correlation_id if ctx is not None else "missing-correlation-id"
    set_request_context(
        RequestContext(
            correlation_id=correlation_id,
            service="worker-overflow",
            user_id=req.user_id,
            tier=req.tier,
            operation="process",
        )
    )

    # 1) Safety check (does not consume quota)
    safety = detect_unsafe(req.message)
    if not safety.allowed:
        return {"ok": True, "reply": refusal_message(tone="warm", category=safety.category), "blocked": True}

    # 2) Rate limit
    rl = await limiter.check_and_increment(user_id=req.user_id, tier=req.tier)  # type: ignore[arg-type]
    if not rl.allowed:
        if rl.first_notice:
            return {
                "ok": True,
                "reply": human_reset_message(rl.reset_in_seconds),
                "rate_limited": True,
                "silent": False,
            }
        return {"ok": True, "reply": None, "rate_limited": True, "silent": True}

    # Stub "LLM" latency: slower / more variable for overflow.
    await asyncio.sleep(random.uniform(0.10, 0.35))
    log.info("processed", extra={"extra": {"user_id": req.user_id, "tier": req.tier}})
    return {"ok": True, "reply": "Processed by overflow pool (stub)."}


