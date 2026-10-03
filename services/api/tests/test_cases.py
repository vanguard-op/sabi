"""Unit tests for payment case management (FEAT-009, C-026 to C-029).

The payment module is the isolated store, so these tests bind a fake payment
port onto ``app.state``: they exercise the case rules and the contract's shapes,
status codes, and errors without a running payment service. The cases router is
included directly because the app factory discovers only the modules that have
landed; the port seam is the real integration point.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import make_settings  # type: ignore[import-not-found]
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cases import lifecycle
from app.cases import router as cases_router
from app.cases.ports import (
    InMemoryPaymentLookup,
    PaymentEventView,
    PaymentView,
    RefundView,
    UnavailablePaymentLookup,
)
from app.core.audit import InMemoryAuditLog
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import InMemorySessionStore, SessionManager
from app.db.base import Base
from app.db.models import PaymentCase
from app.main import create_app

_BASE_TIME = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


class FakePaymentStore(InMemoryPaymentLookup):
    """In-memory stand-in for the isolated payment store and its rail refund."""

    def __init__(self) -> None:
        super().__init__()
        self.refund_calls: list[tuple[str, str, str, str]] = []
        self.refund_result = RefundView(status="reversed", refund_reference="rail-refund-1")

    def add_payment(
        self,
        payment_id: str = "pay-1",
        *,
        status: str = "succeeded",
        user_id: str = "user-1",
        **overrides: object,
    ) -> PaymentView:
        values: dict[str, object] = {
            "payment_id": payment_id,
            "user_id": user_id,
            "service_id": "svc-1",
            "reference": "rail-1",
            "payee": "Onitsha South LGA",
            "amount": 500000,
            "currency": "NGN",
            "channel": "app",
            "status": status,
            "created_at": _BASE_TIME,
            "updated_at": _BASE_TIME,
        }
        values.update(overrides)
        record = PaymentView(**values)  # type: ignore[arg-type]
        self.add(record)
        return record

    def seed_event(
        self,
        payment_id: str,
        *,
        status: str = "succeeded",
        actor: str = "rail",
        index: int = 1,
    ) -> None:
        now = _BASE_TIME + timedelta(minutes=1)
        super().add_event(
            PaymentEventView(
                event_id=f"evt-{index}",
                payment_id=payment_id,
                status=status,
                actor=actor,
                occurred_at=now,
                created_at=now,
                detail=None,
            )
        )

    def refund(
        self, *, user_id: str, payment_id: str, reason: str, idempotency_key: str
    ) -> RefundView:
        self.refund_calls.append((user_id, payment_id, reason, idempotency_key))
        return self.refund_result


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
def payment_store() -> FakePaymentStore:
    return FakePaymentStore()


@pytest.fixture
def app(
    db_factory: sessionmaker[Session],
    session_manager: SessionManager,
    payment_store: FakePaymentStore,
) -> Iterator[FastAPI]:
    application = create_app(make_settings())
    application.state.session_factory = db_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=2, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    application.state.cases_payment_lookup = payment_store
    application.state.cases_refund_port = payment_store
    application.include_router(cases_router.router, prefix="/v1")
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


def _seed_case(
    db_factory: sessionmaker[Session],
    *,
    payment_id: str = "pay-1",
    user_id: str = "user-1",
    case_type: str = "failed_no_delivery",
    status: str = "open",
    case_id: str | None = None,
) -> PaymentCase:
    with db_factory() as db:
        case = PaymentCase(
            payment_id=payment_id,
            user_id=user_id,
            type=case_type,
            status=status,
            assignee_role="support_operations_agent",
            opened_at=_BASE_TIME,
            updated_at=_BASE_TIME,
        )
        if case_id is not None:
            case.id = case_id
        db.add(case)
        db.commit()
        db.refresh(case)
        return case


# --- C-026: list cases -----------------------------------------------------


def test_list_requires_a_session(client: TestClient) -> None:
    response = client.get("/v1/cases")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_list_returns_own_cases_newest_first(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    _seed_case(db_factory, payment_id="pay-1", case_id="01a00000-0000-7000-8000-000000000001")
    _seed_case(db_factory, payment_id="pay-2", case_id="01a00000-0000-7000-8000-000000000002")
    signed_in.sign_in()

    response = signed_in.client.get("/v1/cases")
    assert response.status_code == 200
    body = response.json()
    assert [case["paymentId"] for case in body["cases"]] == ["pay-2", "pay-1"]
    assert body["nextCursor"] is None
    assert body["cases"][0]["caseId"] == "01a00000-0000-7000-8000-000000000002"


def test_list_excludes_another_users_cases(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    _seed_case(db_factory, payment_id="pay-1", user_id="user-1")
    _seed_case(db_factory, payment_id="pay-2", user_id="user-2")
    signed_in.sign_in("user-1")

    body = signed_in.client.get("/v1/cases").json()
    assert [case["paymentId"] for case in body["cases"]] == ["pay-1"]


def test_list_filters_by_status(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    _seed_case(db_factory, payment_id="pay-1", status="open")
    _seed_case(db_factory, payment_id="pay-2", status="resolved")
    signed_in.sign_in()

    body = signed_in.client.get("/v1/cases", params={"status": "resolved"}).json()
    assert [case["paymentId"] for case in body["cases"]] == ["pay-2"]


def test_list_rejects_an_unknown_status(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    response = signed_in.client.get("/v1/cases", params={"status": "nope"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_list_paginates_with_a_cursor(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    for index in range(3):
        _seed_case(
            db_factory,
            payment_id=f"pay-{index}",
            case_id=f"01a00000-0000-7000-8000-00000000000{index}",
        )
    signed_in.sign_in()

    first = signed_in.client.get("/v1/cases", params={"limit": 2}).json()
    assert len(first["cases"]) == 2
    assert first["nextCursor"] is not None

    second = signed_in.client.get(
        "/v1/cases", params={"limit": 2, "cursor": first["nextCursor"]}
    ).json()
    assert len(second["cases"]) == 1
    assert second["nextCursor"] is None


def test_list_is_rate_limited(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    for _ in range(2):
        assert signed_in.client.get("/v1/cases").status_code == 200
    response = signed_in.client.get("/v1/cases")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


# --- C-027: case detail ----------------------------------------------------


def test_case_detail_returns_case_payment_and_timeline(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    case = _seed_case(db_factory)
    payment_store.add_payment(case.payment_id)
    payment_store.seed_event(case.payment_id)
    signed_in.sign_in()

    response = signed_in.client.get(f"/v1/cases/{case.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["id"] == case.id
    assert body["payment"]["paymentId"] == case.payment_id
    assert body["payment"]["amount"] == 500000
    assert body["timeline"][0]["status"] == "succeeded"


def test_case_detail_is_404_for_an_unknown_case(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    response = signed_in.client.get("/v1/cases/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_case_detail_hides_another_users_case(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    case = _seed_case(db_factory, user_id="user-2")
    signed_in.sign_in("user-1")
    assert signed_in.client.get(f"/v1/cases/{case.id}").status_code == 404


def test_case_detail_degrades_when_the_payment_store_is_unreachable(
    app: FastAPI, signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    case = _seed_case(db_factory)
    app.state.cases_payment_lookup = UnavailablePaymentLookup()
    signed_in.sign_in()

    response = signed_in.client.get(f"/v1/cases/{case.id}")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payment_unavailable"


# --- C-028: dispute --------------------------------------------------------


def test_dispute_opens_a_case(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    case = _seed_case(db_factory)
    signed_in.sign_in()

    response = signed_in.client.post(
        f"/v1/cases/{case.id}/dispute", json={"reason": "The biller did not deliver."}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["openedAt"].endswith("Z")

    with db_factory() as db:
        disputes = db.query(PaymentCase).filter_by(type="disputed").all()
        assert len(disputes) == 1
        assert disputes[0].payment_id == case.payment_id


def test_dispute_blocks_a_second_dispute_for_the_payment(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    case = _seed_case(db_factory)
    _seed_case(db_factory, case_type="disputed", status="open")
    signed_in.sign_in()

    response = signed_in.client.post(f"/v1/cases/{case.id}/dispute", json={"reason": "Again"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_dispute_is_404_for_an_unknown_case(signed_in: SimpleNamespace) -> None:
    signed_in.sign_in()
    response = signed_in.client.post("/v1/cases/missing/dispute", json={"reason": "No such case"})
    assert response.status_code == 404


def test_dispute_rejects_a_blank_reason(
    signed_in: SimpleNamespace, db_factory: sessionmaker[Session]
) -> None:
    case = _seed_case(db_factory)
    signed_in.sign_in()
    response = signed_in.client.post(f"/v1/cases/{case.id}/dispute", json={"reason": "   "})
    assert response.status_code == 422


# --- C-029: refund ---------------------------------------------------------


def test_refund_requests_and_returns_the_rail_result(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    case = _seed_case(db_factory)
    payment_store.add_payment(case.payment_id)
    signed_in.sign_in()

    response = signed_in.client.post(
        f"/v1/payments/{case.payment_id}/refund",
        json={"reason": "Debited without delivery."},
        headers={"Idempotency-Key": "idem-1"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body == {
        "paymentId": case.payment_id,
        "status": "reversed",
        "refundReference": "rail-refund-1",
    }
    assert payment_store.refund_calls == [
        ("user-1", case.payment_id, "Debited without delivery.", "idem-1")
    ]

    with db_factory() as db:
        refunds = db.query(PaymentCase).filter_by(type="refund").all()
        assert len(refunds) == 1
        assert refunds[0].status == "awaiting_provider"


def test_refund_requires_an_idempotency_key(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    case = _seed_case(db_factory)
    payment_store.add_payment(case.payment_id)
    signed_in.sign_in()

    response = signed_in.client.post(
        f"/v1/payments/{case.payment_id}/refund", json={"reason": "Refund"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert payment_store.refund_calls == []


def test_refund_blocks_a_duplicate_before_the_rail(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    case = _seed_case(db_factory)
    payment_store.add_payment(case.payment_id)
    _seed_case(db_factory, case_type="refund", status="awaiting_provider")
    signed_in.sign_in()

    response = signed_in.client.post(
        f"/v1/payments/{case.payment_id}/refund",
        json={"reason": "Refund again"},
        headers={"Idempotency-Key": "idem-2"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert payment_store.refund_calls == []


def test_refund_blocks_when_the_payment_is_already_refunded(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    case = _seed_case(db_factory)
    payment_store.add_payment(case.payment_id, status="refunded")
    signed_in.sign_in()

    response = signed_in.client.post(
        f"/v1/payments/{case.payment_id}/refund",
        json={"reason": "Refund"},
        headers={"Idempotency-Key": "idem-3"},
    )
    assert response.status_code == 409


def test_refund_rejects_a_payment_that_is_not_refundable(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    case = _seed_case(db_factory)
    payment_store.add_payment(case.payment_id, status="pending")
    signed_in.sign_in()

    response = signed_in.client.post(
        f"/v1/payments/{case.payment_id}/refund",
        json={"reason": "Refund"},
        headers={"Idempotency-Key": "idem-4"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_refund_is_404_for_an_unknown_payment(
    signed_in: SimpleNamespace,
) -> None:
    signed_in.sign_in()
    response = signed_in.client.post(
        "/v1/payments/missing/refund",
        json={"reason": "Refund"},
        headers={"Idempotency-Key": "idem-5"},
    )
    assert response.status_code == 404


def test_refund_hides_another_users_payment(
    signed_in: SimpleNamespace,
    db_factory: sessionmaker[Session],
    payment_store: FakePaymentStore,
) -> None:
    payment_store.add_payment("pay-2", user_id="user-2")
    signed_in.sign_in("user-1")
    response = signed_in.client.post(
        "/v1/payments/pay-2/refund",
        json={"reason": "Refund"},
        headers={"Idempotency-Key": "idem-6"},
    )
    assert response.status_code == 404
    assert payment_store.refund_calls == []


# --- Case lifecycle: service windows and escalation (FEAT-009) -------------


def _seed_case_case_type(
    case_type: str,
    *,
    status: str,
    opened_at: datetime | None = None,
) -> PaymentCase:
    """An unsaved PaymentCase for the pure lifecycle rules (no database)."""
    return PaymentCase(
        id="case-lifecycle-1",
        payment_id="pay-1",
        user_id="user-1",
        type=case_type,
        status=status,
        assignee_role="support_operations_agent",
        opened_at=opened_at or datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
        updated_at=opened_at or datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
    )


def test_service_windows_match_the_operations_document() -> None:
    assert lifecycle.service_window_days("failed_no_delivery") == 3
    assert lifecycle.service_window_days("refund") == 5
    assert lifecycle.service_window_days("disputed") == 7
    assert lifecycle.service_window_days("receipt_missing") == 2
    assert lifecycle.service_window_days("unknown") is None


def test_business_day_arithmetic_skips_the_weekend() -> None:
    # Friday 2026-10-02 plus one business day lands on Monday 2026-10-05.
    friday = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    assert lifecycle.add_business_days(friday, 1) == datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def test_active_case_past_its_window_escalates() -> None:
    case = _seed_case_case_type("failed_no_delivery", status="awaiting_provider")
    # A 3-business-day window opened Friday closes end of Wednesday; Thursday
    # is past it.
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert lifecycle.exceeds_service_window(case, now) is True
    breaches = lifecycle.find_breaches([case], now)
    assert [breach.case_id for breach in breaches] == [case.id]


def test_case_within_its_window_does_not_escalate() -> None:
    case = _seed_case_case_type("refund", status="awaiting_provider")
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)  # Monday, within 5 days
    assert lifecycle.exceeds_service_window(case, now) is False


def test_naive_opened_at_is_read_as_utc_against_an_aware_clock() -> None:
    # SQLite returns a naive datetime for a DateTime(timezone=True) column
    # while the escalation job's clock is aware; the window must still resolve
    # rather than raise, and report its deadline on the UTC timeline.
    case = _seed_case_case_type(
        "failed_no_delivery",
        status="awaiting_provider",
        opened_at=datetime(2026, 10, 5, 9, 0),
    )
    assert lifecycle.window_deadline(case) == datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def test_naive_opened_at_past_its_window_escalates() -> None:
    case = _seed_case_case_type(
        "failed_no_delivery",
        status="awaiting_provider",
        opened_at=datetime(2026, 10, 5, 9, 0),
    )
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert lifecycle.exceeds_service_window(case, now) is True
    assert [breach.case_id for breach in lifecycle.find_breaches([case], now)] == [case.id]


def test_naive_opened_at_within_its_window_does_not_escalate() -> None:
    case = _seed_case_case_type(
        "refund",
        status="awaiting_provider",
        opened_at=datetime(2026, 10, 5, 9, 0),
    )
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    assert lifecycle.exceeds_service_window(case, now) is False


def test_aware_opened_at_is_unchanged_against_an_aware_clock() -> None:
    # The PostgreSQL path returns aware timestamps; the comparison and the
    # deadline are exactly as before.
    case = _seed_case_case_type(
        "failed_no_delivery",
        status="awaiting_provider",
        opened_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
    )
    assert lifecycle.window_deadline(case) == datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert lifecycle.exceeds_service_window(case, now) is True


def test_resolved_or_closed_case_never_escalates() -> None:
    now = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    for status in ("resolved", "closed"):
        case = _seed_case_case_type("disputed", status=status)
        assert lifecycle.exceeds_service_window(case, now) is False


def test_case_transitions_follow_the_state_machine() -> None:
    assert lifecycle.can_transition("open", "awaiting_provider") is True
    assert lifecycle.can_transition("awaiting_provider", "escalated") is True
    assert lifecycle.can_transition("escalated", "resolved") is True
    assert lifecycle.can_transition("resolved", "closed") is True
    assert lifecycle.can_transition("closed", "open") is False
