"""Fixtures for the API-service integration and acceptance tests.

Run in a process where only ``services/api`` is on ``sys.path`` (the API service
and the AI service each expose a top-level ``app`` package, so they cannot share an
interpreter). The command that runs this directory sets that up; see
``tests/README.md``.

Reference: CONTRACTS.md, DELIVERY.md, roadmap.md Phase 1.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_ROOT = Path(__file__).resolve().parents[2]
_API_ROOT = _ROOT / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.core.audit import InMemoryAuditLog  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter  # noqa: E402
from app.core.sessions import (  # noqa: E402
    InMemorySessionStore,
    SessionKind,
    SessionManager,
)
from app.db.base import Base  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        session_secret="gate-session-secret",
        recovery_code_pepper="gate-recovery-pepper",
    )


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


@pytest.fixture
def api_app(settings: Settings, db_session_factory: sessionmaker[Session]) -> Iterator[FastAPI]:
    """The real API service, built by its own factory, over in-memory stores."""

    from app.main import create_app

    application = create_app(settings)
    application.state.session_factory = db_session_factory
    application.state.session_manager = SessionManager(settings, InMemorySessionStore())
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1000, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    yield application


@pytest.fixture
def api_client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as client:
        yield client


@pytest.fixture
def session_manager(api_app: FastAPI) -> SessionManager:
    return api_app.state.session_manager


def sign_in(
    client: TestClient,
    manager: SessionManager,
    *,
    kind: SessionKind = SessionKind.USER,
    role: str | None = None,
    mfa_verified: bool = False,
) -> None:
    token, _ = manager.issue(user_id="gate-user", kind=kind, role=role, mfa_verified=mfa_verified)
    client.cookies.set(manager.settings.session_cookie_name, token)


@pytest.fixture
def sign_in_as():
    return sign_in


@pytest.fixture
def seed_user(db_session_factory: sessionmaker[Session]):
    """Create a real account row so account-owner surfaces resolve it.

    The session cookie carries only a user id; the account and channel surfaces
    look that id up, so an integration test must seed the row the way
    registration does rather than mint a session for an unknown id.
    """

    from app.db.models import User

    def _seed(**overrides):
        values = {
            "display_name": "Ngozi",
            "locale": "en",
            "preferred_channel": "app",
            "kyc_status": "unverified",
            "account_status": "active",
        }
        values.update(overrides)
        with db_session_factory() as db:
            user = User(**values)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id

    return _seed


@pytest.fixture
def signed_in_user(api_client, session_manager, seed_user, sign_in_as):
    """A client authenticated as a freshly seeded account owner."""

    user_id = seed_user()
    sign_in_as(api_client, session_manager)
    # Reissue the cookie bound to the seeded user id.
    token, _ = session_manager.issue(user_id=user_id)
    api_client.cookies.set(session_manager.settings.session_cookie_name, token)
    return user_id
