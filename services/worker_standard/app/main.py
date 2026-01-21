from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel, Field

from services.common.app_factory import create_app
from services.common.logging import get_logger
from services.common.request_context import RequestContext, get_request_context, set_request_context


app = create_app(service="worker-standard")
log = get_logger("worker-standard")


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
            service="worker-standard",
            user_id=req.user_id,
            tier=req.tier,
            operation="process",
        )
    )

    # Stub "LLM" latency: medium.
    await asyncio.sleep(random.uniform(0.05, 0.15))
    log.info("processed", extra={"extra": {"user_id": req.user_id, "tier": req.tier}})
    return {"ok": True, "reply": "Processed by standard pool (stub)."}


