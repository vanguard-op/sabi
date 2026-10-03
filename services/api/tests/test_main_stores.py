"""Unit tests for the store selection and cache probe in the app factory.

The factory must build the store the settings resolved to, and a selected Redis
that cannot be reached must stop the boot rather than silently run sessions and
rate limits in memory.
"""

from __future__ import annotations

from typing import Any

import pytest
from helpers import make_settings

from app.core.rate_limit import InMemoryRateLimitStore, RedisRateLimitStore
from app.core.sessions import InMemorySessionStore, RedisSessionStore
from app.main import _build_rate_limit_store, _build_session_store, _probe_redis


def test_development_builds_in_memory_stores() -> None:
    settings = make_settings()
    assert isinstance(_build_session_store(settings), InMemorySessionStore)
    assert isinstance(_build_rate_limit_store(settings), InMemoryRateLimitStore)


def test_staging_without_a_cache_builds_in_memory_stores() -> None:
    settings = make_settings(
        environment="staging",
        cache_url="",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
    )
    assert isinstance(_build_session_store(settings), InMemorySessionStore)
    assert isinstance(_build_rate_limit_store(settings), InMemoryRateLimitStore)


def test_development_with_a_cache_still_builds_in_memory_stores() -> None:
    # The development default is in memory regardless of a configured cache;
    # only a hosted environment opts into Redis by default.
    settings = make_settings(cache_url="redis://cache.internal:6379/0")
    assert isinstance(_build_session_store(settings), InMemorySessionStore)
    assert isinstance(_build_rate_limit_store(settings), InMemoryRateLimitStore)


def test_a_reachable_cache_builds_redis_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    def _noop_probe(_url: str) -> None:
        return None

    monkeypatch.setattr("app.main._probe_redis", _noop_probe)
    settings = make_settings(
        environment="staging",
        cache_url="redis://cache.internal:6379/0",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
    )
    assert isinstance(_build_session_store(settings), RedisSessionStore)
    assert isinstance(_build_rate_limit_store(settings), RedisRateLimitStore)


def test_an_unreachable_cache_fails_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_url: str) -> None:
        raise RuntimeError("cache_url is unreachable")

    monkeypatch.setattr("app.main._probe_redis", _boom)
    settings = make_settings(
        environment="staging",
        cache_url="redis://cache.internal:6379/0",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
    )
    with pytest.raises(RuntimeError):
        _build_session_store(settings)
    with pytest.raises(RuntimeError):
        _build_rate_limit_store(settings)


def test_probe_pings_and_closes_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    events: dict[str, Any] = {}

    class _Client:
        def ping(self) -> bool:
            events["pinged"] = True
            return True

        def close(self) -> None:
            events["closed"] = True

    class _Redis:
        @staticmethod
        def from_url(url: str, decode_responses: bool) -> _Client:
            events["url"] = url
            return _Client()

    import redis

    monkeypatch.setattr(redis, "Redis", _Redis)
    _probe_redis("redis://cache.internal:6379/0")
    assert events["url"] == "redis://cache.internal:6379/0"
    assert events["pinged"] is True
    assert events["closed"] is True


def test_probe_raises_and_closes_when_ping_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    events: dict[str, Any] = {}

    class _Client:
        def ping(self) -> bool:
            raise ConnectionError("refused")

        def close(self) -> None:
            events["closed"] = True

    class _Redis:
        @staticmethod
        def from_url(url: str, decode_responses: bool) -> _Client:
            return _Client()

    import redis

    monkeypatch.setattr(redis, "Redis", _Redis)
    with pytest.raises(RuntimeError):
        _probe_redis("redis://cache.internal:6379/0")
    assert events["closed"] is True
