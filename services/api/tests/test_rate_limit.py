import pytest

from app.core.errors import APIError
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter


def test_limit_is_enforced() -> None:
    limiter = RateLimiter(InMemoryRateLimitStore(), default_limit=2, default_window_seconds=60)
    limiter.check("auth:127.0.0.1")
    limiter.check("auth:127.0.0.1")
    with pytest.raises(APIError) as error:
        limiter.check("auth:127.0.0.1")
    assert error.value.status_code == 429
    assert error.value.code == "rate_limited"
    assert "Retry-After" in (error.value.headers or {})


def test_keys_are_counted_independently() -> None:
    limiter = RateLimiter(InMemoryRateLimitStore(), default_limit=1, default_window_seconds=60)
    limiter.check("auth:one")
    limiter.check("auth:two")  # different key, still allowed


def test_window_resets() -> None:
    clock = {"now": 0.0}
    store = InMemoryRateLimitStore(clock=lambda: clock["now"])
    limiter = RateLimiter(store, default_limit=1, default_window_seconds=10)
    limiter.check("k")
    with pytest.raises(APIError):
        limiter.check("k")
    clock["now"] = 11.0
    limiter.check("k")
