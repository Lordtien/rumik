from __future__ import annotations

import time
import uuid
from typing import Callable, Optional

from fastapi import FastAPI, Request, Response

from services.common.logging import get_logger
from services.common.request_context import RequestContext, ServiceName, set_request_context


CORRELATION_ID_HEADER = "X-Correlation-Id"


def _get_or_create_correlation_id(request: Request) -> str:
    incoming = request.headers.get(CORRELATION_ID_HEADER)
    if incoming and len(incoming) <= 128:
        return incoming
    return str(uuid.uuid4())


def install_request_context_middleware(
    app: FastAPI,
    *,
    service: ServiceName,
    slow_ms_threshold: float = 250.0,
) -> None:
    log = get_logger(f"{service}.http")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Callable):
        correlation_id = _get_or_create_correlation_id(request)
        set_request_context(RequestContext(correlation_id=correlation_id, service=service))

        start = time.perf_counter()
        response: Optional[Response] = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if response is not None:
                response.headers[CORRELATION_ID_HEADER] = correlation_id

            if elapsed_ms >= slow_ms_threshold:
                log.warning(
                    "slow_request",
                    extra={
                        "extra": {
                            "path": str(request.url.path),
                            "method": request.method,
                            "status_code": getattr(response, "status_code", None),
                            "elapsed_ms": round(elapsed_ms, 2),
                        }
                    },
                )


