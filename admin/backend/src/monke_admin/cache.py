"""In-memory TTL cache for query results (one Render instance, so no shared store is needed)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any


class TTLCache:
    def __init__(self, ttl_s: float = 300, clock: Callable[[], float] = time.monotonic, max_entries: int = 512):
        self._ttl = ttl_s
        self._clock = clock
        self._max = max_entries
        self._items: dict[str, tuple[float, Any]] = {}

    async def get_or_compute(self, key: str, compute: Callable[[], Awaitable[Any]], force: bool = False) -> Any:
        now = self._clock()
        hit = self._items.get(key)
        if hit is not None and not force and now - hit[0] < self._ttl:
            return hit[1]
        value = await compute()  # exceptions propagate and are not cached
        if len(self._items) >= self._max:
            self._items = {k: v for k, v in self._items.items() if now - v[0] < self._ttl}
        self._items[key] = (self._clock(), value)
        return value
