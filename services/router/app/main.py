from __future__ import annotations

from pydantic import BaseModel, Field

from services.common.app_factory import create_app
from services.common.logging import get_logger
from services.common.request_context import (
    RequestContext,
    get_request_context,
    set_request_context,
)


app = create_app(service="router")
log = get_logger("router")


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=8000)
    tier: str = Field("free", pattern="^(free|premium|enterprise)$")


@app.post("/chat")
async def chat(req: ChatRequest):
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

    # Stub: Step 2 will route to worker pools based on tier/health/load.
    log.info("chat_received", extra={"extra": {"user_id": req.user_id, "tier": req.tier}})
    return {
        "reply": "Got it. (stubbed router response)",
        "tier": req.tier,
    }


