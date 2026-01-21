from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx

PoolName = Literal["priority", "standard", "overflow"]


@dataclass
class PoolConfig:
    name: PoolName
    base_url: str
    max_concurrency: int
    health_path: str = "/healthz"
    process_path: str = "/process"


@dataclass
class PoolState:
    healthy: bool = False
    last_health_check_s: float = 0.0
    last_error: Optional[str] = None
    inflight: int = 0
    ewma_latency_ms: float = 0.0


class PoolManager:
    def __init__(self, configs: list[PoolConfig]) -> None:
        self.configs = {c.name: c for c in configs}
        self.state = {c.name: PoolState() for c in configs}
        self._semaphores = {c.name: asyncio.Semaphore(c.max_concurrency) for c in configs}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=1.0, read=5.0, write=5.0, pool=1.0),
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=200),
        )
        self._health_task: Optional[asyncio.Task] = None

    async def aclose(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
        await self._client.aclose()

    async def start_health_polling(self, interval_s: float = 1.0) -> None:
        if self._health_task is not None:
            return

        async def loop():
            while True:
                await self._poll_all()
                await asyncio.sleep(interval_s)

        self._health_task = asyncio.create_task(loop())

    async def _poll_all(self) -> None:
        async def poll_one(name: PoolName) -> None:
            cfg = self.configs[name]
            st = self.state[name]
            st.last_health_check_s = time.time()
            try:
                r = await self._client.get(f"{cfg.base_url}{cfg.health_path}")
                st.healthy = r.status_code == 200
                st.last_error = None if st.healthy else f"status={r.status_code}"
            except Exception as e:  # noqa: BLE001
                st.healthy = False
                st.last_error = type(e).__name__

        await asyncio.gather(*(poll_one(name) for name in self.configs.keys()))

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, cfg in self.configs.items():
            st = self.state[name]
            out[name] = {
                "base_url": cfg.base_url,
                "max_concurrency": cfg.max_concurrency,
                "healthy": st.healthy,
                "last_error": st.last_error,
                "inflight": st.inflight,
                "ewma_latency_ms": round(st.ewma_latency_ms, 2),
                "last_health_check_s": st.last_health_check_s,
            }
        return out

    def _record_latency(self, name: PoolName, latency_ms: float) -> None:
        st = self.state[name]
        # EWMA smoothing; higher alpha = faster reaction.
        alpha = 0.2
        st.ewma_latency_ms = latency_ms if st.ewma_latency_ms == 0 else (alpha * latency_ms + (1 - alpha) * st.ewma_latency_ms)

    async def call_process(
        self,
        *,
        pool: PoolName,
        payload: dict[str, Any],
        max_queue_wait_s: float = 0.0,
    ) -> httpx.Response:
        cfg = self.configs[pool]
        sem = self._semaphores[pool]
        st = self.state[pool]

        # Admission control with optional bounded waiting.
        #
        # Note: asyncio.Semaphore does not provide a stable acquire_nowait() API across versions.
        # For "no wait" we check locked() and then acquire (which will not block if unlocked).
        if max_queue_wait_s > 0:
            await asyncio.wait_for(sem.acquire(), timeout=max_queue_wait_s)
        else:
            if sem.locked():
                raise PoolOverloaded(pool)
            await sem.acquire()

        st.inflight += 1
        start = time.perf_counter()
        try:
            return await self._client.post(f"{cfg.base_url}{cfg.process_path}", json=payload)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._record_latency(pool, elapsed_ms)
            st.inflight -= 1
            sem.release()


class PoolOverloaded(RuntimeError):
    def __init__(self, pool: PoolName) -> None:
        super().__init__(f"pool_overloaded:{pool}")
        self.pool = pool


def load_pool_configs_from_env() -> list[PoolConfig]:
    # Defaults assume local dev (no docker compose yet).
    priority_url = os.getenv("PRIORITY_WORKER_URL", "http://localhost:8001")
    standard_url = os.getenv("STANDARD_WORKER_URL", "http://localhost:8002")
    overflow_url = os.getenv("OVERFLOW_WORKER_URL", "http://localhost:8003")

    # Default concurrency is intentionally small; tune via env for load tests.
    pri_c = int(os.getenv("PRIORITY_MAX_CONCURRENCY", "50"))
    std_c = int(os.getenv("STANDARD_MAX_CONCURRENCY", "80"))
    ovf_c = int(os.getenv("OVERFLOW_MAX_CONCURRENCY", "30"))

    return [
        PoolConfig(name="priority", base_url=priority_url, max_concurrency=pri_c),
        PoolConfig(name="standard", base_url=standard_url, max_concurrency=std_c),
        PoolConfig(name="overflow", base_url=overflow_url, max_concurrency=ovf_c),
    ]

