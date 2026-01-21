from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from services.common.logging import get_logger
from services.common.mongo import get_db


log = get_logger("analytics")

_queue: Optional[asyncio.Queue[dict[str, Any]]] = None
_task: Optional[asyncio.Task] = None
_stopping = False
_dropped = 0


def _get_queue() -> asyncio.Queue[dict[str, Any]]:
    global _queue
    if _queue is None:
        # Bounded queue; events are dropped when full.
        _queue = asyncio.Queue(maxsize=10_000)
    return _queue


async def start() -> None:
    """Start background flusher if not already running."""
    global _task, _stopping
    if _task is not None:
        return
    _stopping = False

    async def _run() -> None:
        db = get_db()
        col = db.analytics_events

        queue = _get_queue()
        batch: list[dict[str, Any]] = []

        async def flush() -> None:
            nonlocal batch
            if not batch:
                return
            to_insert = batch
            batch = []
            try:
                await col.insert_many(to_insert, ordered=False)
            except Exception as e:  # noqa: BLE001
                log.warning("analytics_flush_failed", extra={"extra": {"err": type(e).__name__}})

        last_flush = time.perf_counter()
        flush_interval_s = 0.5
        max_batch_size = 100

        while not _stopping or not queue.empty():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=flush_interval_s)
                batch.append(item)
            except asyncio.TimeoutError:
                # periodic flush even if nothing new
                pass

            now = time.perf_counter()
            if len(batch) >= max_batch_size or (batch and now - last_flush >= flush_interval_s):
                await flush()
                last_flush = now

        # Final flush on shutdown
        await flush()
        if _dropped:
            log.warning("analytics_events_dropped", extra={"extra": {"dropped": _dropped}})

    _task = asyncio.create_task(_run())


async def stop() -> None:
    """Signal background flusher to stop and wait for drain."""
    global _task, _stopping
    if _task is None:
        return
    _stopping = True
    await _task
    _task = None


async def track(event: dict[str, Any]) -> None:
    """Enqueue analytics event without blocking critical path.

    Guarantees:
    - No network/DB IO on the caller.
    - If queue is full, event is dropped and a counter is recorded.
    """
    global _dropped
    q = _get_queue()
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        _dropped += 1

