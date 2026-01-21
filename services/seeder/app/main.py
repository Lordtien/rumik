from __future__ import annotations

from pydantic import BaseModel, Field

from services.common.app_factory import create_app
from services.common.logging import get_logger
from services.common.request_context import RequestContext, get_request_context, set_request_context


app = create_app(service="seeder")
log = get_logger("seeder")


class SeedRequest(BaseModel):
    total_users: int = Field(1_000, ge=1, le=10_000_000)


@app.post("/seed")
async def seed(req: SeedRequest):
    ctx = get_request_context()
    correlation_id = ctx.correlation_id if ctx is not None else "missing-correlation-id"
    set_request_context(
        RequestContext(
            correlation_id=correlation_id,
            service="seeder",
            operation="seed",
        )
    )
    # Stub only: real seeding is Part 1/2 via scripts (and a one-shot compose service).
    log.info("seed_requested", extra={"extra": {"total_users": req.total_users}})
    return {"ok": True, "note": "Seeder is stubbed; real seeding comes in Part 1."}


