"""Unit tests for federal government payment flows (FEAT-006, C-030 to C-032).

The payment module is the isolated store, so these tests bind fake payment and
FTeR ports onto ``app.state``: they exercise the federal rules and the
contract's shapes, status codes, and errors without a running payment or
e-receipt service. The federal router is included directly because the app
factory discovers only the modules that have landed; the port seam is the real
integration point.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import make_settings  # type: ignore[import-not-found]
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import InMemoryAuditLog
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import InMemorySessionStore, SessionManager
from app.db.base import Base
from app.db.models import PaymentCase, Receipt, Service, User
from app.federal import router as federal_router
from app.federal.models import FederalCollection
from app.federal.ports import (
    FederalReceiptView,
    InMemoryPaymentLookup,
    InMemoryReceiptSource,
    PaymentView,
)
from app.main import create_app

_BASE_TIME = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


@pytest.fixture
def db_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_manager() -> SessionManager:
    return SessionManager(make_settings(), InMemorySessionStore())


@pytest.fixture
def payment_store() -> InMemoryPaymentLookup:
    return InMemoryPaymentLookup()


@pytest.fixture
def receipt_source() -> InMemoryReceiptSource:
    return InMemoryReceiptSource()


@pytest.fixture
def app(
    db_factory: sessionmaker[Session],
    session_manager: SessionManager,
    payment_store: InMemoryPaymentLookup,
    receipt_source: InMemoryReceiptSource,
) -> Iterator[FastAPI]:
    application = create_app(make_settings())
    application.state.session_factory = db_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=100, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    application.state.federal_payment_lookup = payment_store
    application.state.federal_receipt_source = receipt_source
    application.include_router(federal_router.router, prefix="/v1")
    yield application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(app: FastAPI, client: TestClient, session_manager: SessionManager):  # type: ignore[no-untyped-def]
    def sign_in(user_id: str = "user-1") -> None:
        token, _ = session_manager.issue(user_id=user_id)
        client.cookies.set(session_manager.settings.session_cookie_name, token)

    return SimpleNamespace(client=client, sign_in=sign_in)


def _user(db: Session, user_id: str = "user-1") -> User:
    user = User(id=user_id, locale="en", preferred_channel="app")
    db.add(user)
    db.flush()
    return user


def _seed_service(
    db_factory: sessionmaker[Session],
    *,
    service_id: str = "svc-1",
    service_type: str = "government",
    known_amount: int | None = 2500000,
    collection: str | None = "current",
    requires_reference: bool = False,
    reference_instructions: str | None = None,
) -> Service:
    """A government service with, by default, a current federal collection."""
    with db_factory() as db:
        _user(db)
        service = Service(
            id=service_id,
            type=service_type,
            name="Land Use Charge",
            collecting_body="Kano State Internal Revenue",
            category="government",
            aliases=[],
            known_amount=known_amount,
            currency="NGN",
            status="active",
        )
        db.add(service)
        db.flush()
        if collection is not None:
            db.add(
                FederalCollection(
                    service_id=service_id,
                    account_reference="treasury-001",
                    requires_reference=requires_reference,
                    instructions="Pay through the designated treasury account.",
                    reference_instructions=reference_instructions,
                    status=collection,
                )
            )
        db.commit()
        db.refresh(service)
        return service


def _seed_payment(
    store: InMemoryPaymentLookup,
    payment_id: str = "pay-1",
    *,
    status: str = "succeeded",
    user_id: str = "user-1",
    reference: str | None = "rail-1",
) -> PaymentView:
    record = PaymentView(
        payment_id=payment_id,
        user_id=user_id,
        service_id="svc-1",
        reference=reference,
        payee="Kano State Internal Revenue",
        amount=2500000,
        currency="NGN",
        status=status,
        channel="app",
        created_at=_BASE_TIME,
        updated_at=_BASE_TIME,
    )
    store.add(record)
    return record


def _seed_case(
    db_factory: sessionmaker[Session],
    *,
    payment_id: str = "pay-1",
    user_id: str = "user-1",
    case_type: str = "receipt_missing",
    status: str = "open",
) -> PaymentCase:
    with db_factory() as db:
        _user(db, user_id)
        case = PaymentCase(
            payment_id=payment_id,
            user_id=user_id,
            type=case_type,
            status=status,
            assignee_role="reconciliation_officer",
            opened_at=_BASE_TIME,
            updated_at=_BASE_TIME,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case


# --- C-030: prepare --------------------------------------------------------


def test_prepare_requires_a_session(client: TestClient) -> None:
    response = client.post("/v1/payments/federal/prepare", json={"serviceId": "svc-1"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_prepare_returns_the_obligation(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
) -> None:
    _seed_service(db_factory)
    signed_in.sign_in()

    response = signed_in.client.post("/v1/payments/federal/prepare", json={"serviceId": "svc-1"})
    assert response.status_code == 200
    assert response.json() == {
        "serviceId": "svc-1",
        "collectingBody": "Kano State Internal Revenue",
        "amount": 2500000,
        "currency": "NGN",
        "requiresReference": False,
        "instructions": "Pay through the designated treasury account.",
    }


def test_prepare_explains_a_missing_required_reference(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
) -> None:
    _seed_service(
        db_factory,
        requires_reference=True,
        reference_instructions="Get an assessment number from the agency portal.",
    )
    signed_in.sign_in()

    response = signed_in.client.post("/v1/payments/federal/prepare", json={"serviceId": "svc-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["requiresReference"] is True
    assert body["instructions"] == "Get an assessment number from the agency portal."


def test_prepare_resolves_a_supplied_reference_to_general_instructions(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
) -> None:
    _seed_service(
        db_factory,
        requires_reference=True,
        reference_instructions="Get an assessment number from the agency portal.",
    )
    signed_in.sign_in()

    response = signed_in.client.post(
        "/v1/payments/federal/prepare",
        json={"serviceId": "svc-1", "payerReference": "ASM-9981"},
    )
    assert response.status_code == 200
    assert response.json()["instructions"] == "Pay through the designated treasury account."


def test_prepare_rejects_an_unknown_service(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    response = signed_in.client.post("/v1/payments/federal/prepare", json={"serviceId": "missing"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_prepare_rejects_a_non_federal_service(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
) -> None:
    _seed_service(db_factory, collection=None)
    signed_in.sign_in()
    response = signed_in.client.post("/v1/payments/federal/prepare", json={"serviceId": "svc-1"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_prepare_rejects_a_non_government_service_with_a_collection(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
) -> None:
    _seed_service(db_factory, service_type="biller")
    signed_in.sign_in()
    response = signed_in.client.post("/v1/payments/federal/prepare", json={"serviceId": "svc-1"})
    assert response.status_code == 422


def test_prepare_reports_a_changed_collection_account(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
) -> None:
    _seed_service(db_factory, collection="changed")
    signed_in.sign_in()
    response = signed_in.client.post("/v1/payments/federal/prepare", json={"serviceId": "svc-1"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


# --- C-031: receipt --------------------------------------------------------


def test_receipt_requires_a_session(client: TestClient) -> None:
    response = client.get("/v1/payments/federal/pay-1/receipt")
    assert response.status_code == 401


def test_receipt_awaits_the_official_receipt_when_the_source_has_none(
    signed_in: SimpleNamespace,
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store)
    signed_in.sign_in()

    response = signed_in.client.get("/v1/payments/federal/pay-1/receipt")
    assert response.status_code == 202
    assert response.json() == {"status": "awaiting_receipt", "retryAfterSeconds": 30}


def test_receipt_stores_and_returns_the_fter(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: InMemoryPaymentLookup,
    receipt_source: InMemoryReceiptSource,
) -> None:
    _seed_payment(payment_store)
    receipt_source.add(
        "pay-1",
        FederalReceiptView(
            receipt_number="FTER-2026-0001",
            verification_status="verified",
            document_ref="fter/pay-1.pdf",
            issued_at=_BASE_TIME,
        ),
    )
    signed_in.sign_in()

    response = signed_in.client.get("/v1/payments/federal/pay-1/receipt")
    assert response.status_code == 200
    body = response.json()
    assert body["receiptNumber"] == "FTER-2026-0001"
    assert body["verificationStatus"] == "verified"
    assert body["receiptId"]

    with db_factory() as db:
        stored = db.query(Receipt).filter_by(payment_id="pay-1", kind="official_e_receipt").one()
        assert stored.id == body["receiptId"]
        assert stored.receipt_number == "FTER-2026-0001"


def test_receipt_is_idempotent_across_polls(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: InMemoryPaymentLookup,
    receipt_source: InMemoryReceiptSource,
) -> None:
    _seed_payment(payment_store)
    receipt_source.add(
        "pay-1",
        FederalReceiptView(receipt_number="FTER-2026-0001", verification_status="verified"),
    )
    signed_in.sign_in()

    first = signed_in.client.get("/v1/payments/federal/pay-1/receipt").json()
    second = signed_in.client.get("/v1/payments/federal/pay-1/receipt").json()
    assert first["receiptId"] == second["receiptId"]
    with db_factory() as db:
        assert db.query(Receipt).filter_by(payment_id="pay-1").count() == 1


def test_receipt_is_404_for_an_unknown_payment(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    response = signed_in.client.get("/v1/payments/federal/missing/receipt")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_receipt_hides_another_users_payment(
    signed_in: SimpleNamespace,
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store, user_id="user-2")
    signed_in.sign_in("user-1")
    assert signed_in.client.get("/v1/payments/federal/pay-1/receipt").status_code == 404


def test_receipt_conflicts_when_the_payment_did_not_succeed(
    signed_in: SimpleNamespace,
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store, status="pending")
    signed_in.sign_in()
    response = signed_in.client.get("/v1/payments/federal/pay-1/receipt")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


# --- C-032: reconcile ------------------------------------------------------


def test_reconcile_requires_a_session(client: TestClient) -> None:
    response = client.post("/v1/payments/federal/pay-1/reconcile", json={"reason": "Missing"})
    assert response.status_code == 401


def test_reconcile_opens_a_case(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store)
    signed_in.sign_in()

    response = signed_in.client.post(
        "/v1/payments/federal/pay-1/reconcile",
        json={"reason": "The agency record does not show this payment."},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "open"
    assert body["caseId"]

    with db_factory() as db:
        case = db.query(PaymentCase).filter_by(payment_id="pay-1").one()
        assert case.id == body["caseId"]
        assert case.type == "receipt_missing"
        assert case.assignee_role == "reconciliation_officer"


def test_reconcile_blocks_a_second_open_case(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store)
    _seed_case(db_factory)
    signed_in.sign_in()

    response = signed_in.client.post(
        "/v1/payments/federal/pay-1/reconcile", json={"reason": "Again"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_reconcile_is_404_for_an_unknown_payment(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    response = signed_in.client.post(
        "/v1/payments/federal/missing/reconcile", json={"reason": "Missing"}
    )
    assert response.status_code == 404


def test_reconcile_hides_another_users_payment(
    signed_in: SimpleNamespace,
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store, user_id="user-2")
    signed_in.sign_in("user-1")
    response = signed_in.client.post(
        "/v1/payments/federal/pay-1/reconcile", json={"reason": "Missing"}
    )
    assert response.status_code == 404


def test_reconcile_rejects_a_blank_reason(
    signed_in: SimpleNamespace,
    payment_store: InMemoryPaymentLookup,
) -> None:
    _seed_payment(payment_store)
    signed_in.sign_in()
    response = signed_in.client.post("/v1/payments/federal/pay-1/reconcile", json={"reason": "   "})
    assert response.status_code == 422
