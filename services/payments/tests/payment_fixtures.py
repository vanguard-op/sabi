"""Shared fixtures for the payment module's unit tests.

Tests never need Postgres: the isolated store is exercised on an in-memory
SQLite engine, and the rail is a double so each execution outcome is explicit.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from sabi_payments.core.config import PaymentSettings
from sabi_payments.core.rail import RailCharge, RailOutcome
from sabi_payments.db.base import Base
from sabi_payments.payments.service import PaymentService


class FakeRail:
    """A rail double returning a fixed outcome, recording every charge."""

    def __init__(self, outcome: RailOutcome | None = None) -> None:
        self.outcome = outcome or RailOutcome(status="succeeded", reference="RAIL-1")
        self.charges: list[RailCharge] = []

    def charge(self, request: RailCharge) -> RailOutcome:
        self.charges.append(request)
        return self.outcome


@pytest.fixture
def settings() -> PaymentSettings:
    return PaymentSettings(
        _env_file=None,
        payments_database_url="postgresql+psycopg://sabi:secret@localhost:5432/sabi_payments",
        mandate_signing_key="test-key",
        mandate_ttl_seconds=300,
        default_authorisation_limit=5_000_000,
    )


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def rail() -> FakeRail:
    return FakeRail()


@pytest.fixture
def service(
    session_factory: sessionmaker[Session], settings: PaymentSettings, rail: FakeRail
) -> PaymentService:
    return PaymentService(session_factory, settings=settings, rail=rail)
