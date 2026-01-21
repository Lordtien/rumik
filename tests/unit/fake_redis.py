from __future__ import annotations

import time
from typing import Any, Optional


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def incr(self, key: str) -> "FakePipeline":
        self._ops.append(("incr", (key,), {}))
        return self

    def ttl(self, key: str) -> "FakePipeline":
        self._ops.append(("ttl", (key,), {}))
        return self

    async def execute(self) -> list[Any]:
        out: list[Any] = []
        for op, args, kwargs in self._ops:
            fn = getattr(self._redis, op)
            res = await fn(*args, **kwargs)  # type: ignore[misc]
            out.append(res)
        self._ops.clear()
        return out


class FakeRedis:
    """A minimal async Redis mock for unit tests.

    Supports:
    - incr
    - ttl
    - expire
    - set (NX + EX)
    - pipeline with incr+ttl sequence
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._expiry: dict[str, float] = {}  # unix timestamp seconds

    def _purge_if_expired(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and time.time() >= exp:
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    async def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        v = int(self._store.get(key, "0")) + 1
        self._store[key] = str(v)
        return v

    async def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        if key not in self._store:
            return -2  # redis: key does not exist
        exp = self._expiry.get(key)
        if exp is None:
            return -1  # redis: no expiry
        return max(0, int(exp - time.time()))

    async def expire(self, key: str, seconds: int) -> bool:
        self._purge_if_expired(key)
        if key not in self._store:
            return False
        self._expiry[key] = time.time() + seconds
        return True

    async def set(self, key: str, value: str, *, ex: Optional[int] = None, nx: bool = False) -> bool:
        self._purge_if_expired(key)
        if nx and key in self._store:
            return False
        self._store[key] = value
        if ex is not None:
            self._expiry[key] = time.time() + ex
        return True

