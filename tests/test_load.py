from __future__ import annotations

import asyncio
import os
import statistics
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import pytest


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

Tier = Literal["free", "premium", "enterprise"]


@dataclass
class Sample:
    tier: Tier
    ok: bool
    degraded: bool
    blocked: bool
    rate_limited: bool
    silent: bool
    latency_ms: float


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * p
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    return values_sorted[f] * (c - k) + values_sorted[c] * (k - f)


async def run_burst(
    client: httpx.AsyncClient,
    *,
    tier: Tier,
    n: int,
    concurrency: int,
) -> list[Sample]:
    sem = asyncio.Semaphore(concurrency)
    samples: list[Sample] = []

    async def one(i: int) -> None:
        user_id = f"load_{tier}_{uuid.uuid4()}"
        payload = {"user_id": user_id, "message": f"hello {i}", "tier": tier}
        async with sem:
            start = time.perf_counter()
            try:
                r = await client.post("/chat", json=payload)
                latency_ms = (time.perf_counter() - start) * 1000.0
                body: dict[str, Any] = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                samples.append(
                    Sample(
                        tier=tier,
                        ok=r.status_code == 200,
                        degraded=bool(body.get("degraded")),
                        blocked=bool(body.get("blocked")),
                        rate_limited=bool(body.get("rate_limited")),
                        silent=bool(body.get("silent")),
                        latency_ms=latency_ms,
                    )
                )
            except Exception:
                latency_ms = (time.perf_counter() - start) * 1000.0
                samples.append(
                    Sample(
                        tier=tier,
                        ok=False,
                        degraded=True,
                        blocked=False,
                        rate_limited=False,
                        silent=False,
                        latency_ms=latency_ms,
                    )
                )

    await asyncio.gather(*(one(i) for i in range(n)))
    return samples


@pytest.mark.asyncio
async def test_load_profile_prints_and_behaves():
    # Tune via env when running in docker-compose.
    n_free = int(os.getenv("LOAD_N_FREE", "60"))
    n_premium = int(os.getenv("LOAD_N_PREMIUM", "60"))
    n_enterprise = int(os.getenv("LOAD_N_ENTERPRISE", "60"))
    concurrency = int(os.getenv("LOAD_CONCURRENCY", "30"))

    timeout = float(os.getenv("LOAD_TIMEOUT_S", "10.0"))

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=timeout) as client:
        # Interleave bursts so they contend naturally.
        results = await asyncio.gather(
            run_burst(client, tier="enterprise", n=n_enterprise, concurrency=concurrency),
            run_burst(client, tier="premium", n=n_premium, concurrency=concurrency),
            run_burst(client, tier="free", n=n_free, concurrency=concurrency),
        )

    all_samples = [s for batch in results for s in batch]
    assert all_samples, "no samples collected"

    def summarize(tier: Tier) -> dict[str, Any]:
        ss = [s for s in all_samples if s.tier == tier]
        lat = [s.latency_ms for s in ss if s.ok]
        degraded = sum(1 for s in ss if s.degraded)
        ok = sum(1 for s in ss if s.ok)
        return {
            "n": len(ss),
            "ok": ok,
            "degraded": degraded,
            "p50_ms": round(pct(lat, 0.50), 2),
            "p95_ms": round(pct(lat, 0.95), 2),
            "p99_ms": round(pct(lat, 0.99), 2),
        }

    ent = summarize("enterprise")
    pre = summarize("premium")
    fre = summarize("free")

    # Print a mini report (shows in CI / docker compose logs).
    print("\n=== load summary ===")
    print(f"enterprise: {ent}")
    print(f"premium:    {pre}")
    print(f"free:       {fre}")

    # Basic invariants:
    # - Enterprise should not degrade *more* than premium/free.
    assert ent["degraded"] <= pre["degraded"] + 5
    assert ent["degraded"] <= fre["degraded"] + 5

    # - Free should degrade at least as much as premium under contention.
    assert fre["degraded"] >= pre["degraded"]

