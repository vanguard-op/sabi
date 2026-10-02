"""Shared fixtures for the API test suite.

Tests never require Postgres, Redis, or a running process: sessions, rate limits,
and the audit log are in memory, and model tests use an isolated SQLite store.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import make_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import InMemoryAuditLog
from app.core.config import Settings
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import InMemorySessionStore, SessionManager
from app.db.base import Base
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def session_manager(settings: Settings, session_store: InMemorySessionStore) -> SessionManager:
    return SessionManager(settings, session_store)


@pytest.fixture
def app(settings: Settings, session_manager: SessionManager) -> Iterator[FastAPI]:
    application = create_app(settings)
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=2, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    yield application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()
