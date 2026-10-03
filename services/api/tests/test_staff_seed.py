"""Unit tests for the development-only staff account seed.

Covers the safety guard (NFR-024), idempotency, and the property the seed exists
to guarantee: the provisioned credential verifies through the real login service.
"""

from __future__ import annotations

import pytest
from helpers import make_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.audit import InMemoryAuditLog
from app.core.errors import APIError
from app.db.base import Base
from app.staff import service, totp
from app.staff.models import StaffAccount
from app.staff.schemas import StaffLoginRequest
from app.staff.seed import (
    DEFAULT_DEV_STAFF_EMAIL,
    SeedError,
    generate_totp_secret,
    seed_dev_staff,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _non_development(environment: str):
    return make_settings(
        environment=environment,
        session_secret="real-session-secret",
        recovery_code_pepper="real-pepper",
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_guard_rejects_non_development(environment: str) -> None:
    # The guard runs before any database access, so an unbound Session is safe to
    # pass: the refusal must not depend on the store being reachable.
    with pytest.raises(SeedError):
        seed_dev_staff(
            Session(), _non_development(environment), email=DEFAULT_DEV_STAFF_EMAIL, password="x"
        )


def test_seed_is_idempotent_keyed_on_email(db: Session) -> None:
    settings = make_settings()
    first = seed_dev_staff(db, settings, email="Admin@Sabi.ng", password="first-password")
    second = seed_dev_staff(db, settings, email="admin@sabi.ng", password="second-password")
    db.commit()

    assert first.created is True
    assert second.created is False
    assert first.staff_id == second.staff_id
    assert first.totp_secret != second.totp_secret

    rows = db.query(StaffAccount).all()
    assert len(rows) == 1
    assert rows[0].email == "admin@sabi.ng"
    assert rows[0].role == "administrator"
    assert rows[0].status == "active"


def test_seeded_account_authenticates_with_password_and_totp(db: Session) -> None:
    settings = make_settings()
    result = seed_dev_staff(db, settings, email="admin@sabi.ng", password="local-password")
    db.commit()

    account = service.authenticate(
        db,
        settings,
        InMemoryAuditLog(),
        request=StaffLoginRequest(
            email="admin@sabi.ng",
            password="local-password",
            totp=totp.generate(result.totp_secret),
        ),
    )
    assert account.id == result.staff_id
    assert account.role == "administrator"
    assert account.last_login_at is not None


def test_seeded_account_rejects_wrong_password(db: Session) -> None:
    settings = make_settings()
    result = seed_dev_staff(db, settings, email="admin@sabi.ng", password="local-password")

    with pytest.raises(APIError) as excinfo:
        service.authenticate(
            db,
            settings,
            InMemoryAuditLog(),
            request=StaffLoginRequest(
                email="admin@sabi.ng",
                password="wrong-password",
                totp=totp.generate(result.totp_secret),
            ),
        )
    assert excinfo.value.status_code == 401


def test_seed_requires_a_password(db: Session) -> None:
    with pytest.raises(SeedError):
        seed_dev_staff(db, make_settings(), email="admin@sabi.ng", password="")


def test_generated_totp_secret_is_base32_and_verifies_its_own_code() -> None:
    secret = generate_totp_secret()
    assert secret.isalnum() and secret == secret.upper()
    assert totp.verify(secret, totp.generate(secret))
