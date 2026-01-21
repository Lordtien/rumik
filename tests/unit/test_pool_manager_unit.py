from __future__ import annotations

import asyncio

import httpx
import pytest

from services.router.app.pools import PoolConfig, PoolManager, PoolOverloaded


@pytest.mark.asyncio
async def test_pool_manager_overloaded_when_no_capacity():
    mgr = PoolManager([PoolConfig(name="overflow", base_url="http://test", max_concurrency=1)])  # type: ignore[list-item]
    # Replace HTTP client so it never actually connects.
    mgr._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True})))

    # Acquire the only slot.
    await mgr._semaphores["overflow"].acquire()
    try:
        with pytest.raises(PoolOverloaded):
            await mgr.call_process(pool="overflow", payload={"x": 1}, max_queue_wait_s=0.0)
    finally:
        mgr._semaphores["overflow"].release()
        await mgr.aclose()


@pytest.mark.asyncio
async def test_health_polling_marks_pool_healthy():
    mgr = PoolManager([PoolConfig(name="overflow", base_url="http://test", max_concurrency=1)])  # type: ignore[list-item]
    mgr._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200 if req.url.path == "/healthz" else 404))
    )
    await mgr._poll_all()
    assert mgr.state["overflow"].healthy is True
    await mgr.aclose()


@pytest.mark.asyncio
async def test_latency_ewma_updates():
    mgr = PoolManager([PoolConfig(name="overflow", base_url="http://test", max_concurrency=5)])  # type: ignore[list-item]

    async def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/process":
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={"reply": "ok"})
        return httpx.Response(200, json={"status": "ok"})

    mgr._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await mgr.call_process(pool="overflow", payload={"x": 1}, max_queue_wait_s=0.1)
    assert mgr.state["overflow"].ewma_latency_ms > 0
    await mgr.aclose()

