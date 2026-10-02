"""Fixed-window rate limiting for public surfaces.

Counters live in the cache store in production and in memory for development and
tests (architecture.md: rate-limit counters). Exceeding a window returns the
standard envelope with HTTP 429 and a Retry-After header.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

from app.core.errors import APIError, ErrorCode


class RateLimitStore(Protocol):
    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Record one hit and return (count_in_window, seconds_until_reset)."""


class InMemoryRateLimitStore:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = self._clock()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= window_seconds:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
            reset_in = max(1, int(window_seconds - (now - start)))
            return count, reset_in


class RedisRateLimitStore:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        redis_key = f"sabi:ratelimit:{key}"
        pipe = self._client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds, nx=True)
        pipe.ttl(redis_key)
        count, _, ttl = pipe.execute()
        return int(count), max(1, int(ttl))


class RateLimiter:
    def __init__(
        self,
        store: RateLimitStore,
        *,
        default_limit: int = 60,
        default_window_seconds: int = 60,
    ) -> None:
        self._store = store
        self._default_limit = default_limit
        self._default_window = default_window_seconds

    def check(
        self,
        key: str,
        *,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        effective_limit = limit if limit is not None else self._default_limit
        effective_window = window_seconds if window_seconds is not None else self._default_window
        count, reset_in = self._store.hit(key, effective_window)
        if count > effective_limit:
            raise APIError(
                429,
                ErrorCode.RATE_LIMITED,
                "Too many requests. Try again shortly.",
                headers={"Retry-After": str(reset_in)},
            )
