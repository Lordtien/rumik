from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel, Field

from services.common.app_factory import create_app
from services.common.logging import get_logger
from services.common.request_context import RequestContext, get_request_context, set_request_context


app = create_app(service="worker-priority")
log = get_logger("worker-priority")


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
            service="worker-priority",
            user_id=req.user_id,
            tier=req.tier,
            operation="process",
        )
    )

    # Stub "LLM" latency: faster / more stable for priority pool.
    await asyncio.sleep(random.uniform(0.02, 0.06))
    log.info("processed", extra={"extra": {"user_id": req.user_id, "tier": req.tier}})
    return {"ok": True, "reply": "Processed by priority pool (stub)."}


