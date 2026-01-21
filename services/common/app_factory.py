from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.common.http import install_request_context_middleware
from services.common.logging import configure_logging, get_logger
from services.common.request_context import ServiceName


def create_app(*, service: ServiceName) -> FastAPI:
    log_level = os.getenv("LOG_LEVEL", "INFO")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging(log_level)
        log = get_logger(service)
        log.info("startup")
        yield
        log.info("shutdown")

    app = FastAPI(title=f"ira-{service}", lifespan=lifespan)
    install_request_context_middleware(app, service=service)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "service": service}

    @app.get("/readyz")
    async def readyz():
        # Later: verify Mongo/Redis connectivity.
        return {"ready": True, "service": service}

    return app


