from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Mapping, Optional

from services.common.request_context import get_request_context


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        ctx = get_request_context()
        if ctx is not None:
            payload.update(
                {
                    "correlation_id": ctx.correlation_id,
                    "service": ctx.service,
                    "user_id": ctx.user_id,
                    "tier": ctx.tier,
                    "operation": ctx.operation,
                }
            )

        # Attach extra fields if provided.
        extra: Optional[Mapping[str, Any]] = getattr(record, "extra", None)
        if extra:
            payload.update(extra)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    # Replace handlers (idempotent for reload).
    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


