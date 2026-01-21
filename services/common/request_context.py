from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Literal, Optional


ServiceName = Literal[
    "router",
    "worker-priority",
    "worker-standard",
    "worker-overflow",
    "seeder",
]


@dataclass(frozen=True)
class RequestContext:
    correlation_id: str
    service: ServiceName
    user_id: Optional[str] = None
    tier: Optional[str] = None
    operation: Optional[str] = None


_ctx_var: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar(
    "ira_request_context",
    default=None,
)


def set_request_context(ctx: RequestContext) -> None:
    _ctx_var.set(ctx)


def get_request_context() -> Optional[RequestContext]:
    return _ctx_var.get()


