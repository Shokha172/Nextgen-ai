"""In-process sliding-window limiter (per key + per route class).

Documented tradeoff: a single-process limiter is sufficient for one API instance
and is the honest default here. Behind multiple replicas, swap the `_hits` store
for Redis (`INCR`/`EXPIRE`) — the interface is deliberately tiny.
"""
from __future__ import annotations

import time
from collections import deque

from app.core.config import settings
from app.core.errors import RateLimited

_hits: dict[str, deque[float]] = {}
_MAX_KEYS = 20_000


def reset() -> None:
    _hits.clear()


def hit(key: str, *, limit: int | None = None, window_s: int = 60) -> None:
    limit = limit or settings.RATE_LIMIT_PER_MINUTE
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:  # crude memory guard
        _hits.clear()
    q = _hits.setdefault(key, deque())
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= limit:
        retry = int(window_s - (now - q[0])) + 1
        raise RateLimited("Too many requests, slow down", code="rate_limited",
                          details={"retry_after_s": retry})
    q.append(now)
