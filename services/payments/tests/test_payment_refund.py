"""Reversal/refund at the rail and its C-029 surface (FEAT-009).

The refund boundary is keyed by the debit's reference, so a second refund for a
reference is blocked at the rail and by the payment's terminal state. These tests
pin the mock rail's outcomes, the disabled adapter's honesty, and the C-029 wire
shape, including the duplicate and not-refundable edges.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from payment_fixtures import FakeRail
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sabi_payments.core.config import PaymentSettings
from sabi_payments.core.rail import DisabledRail
from sabi_payments.db.base import Base
from sabi_payments.main import create_app
from sabi_payments.payments.service import PaymentService
from sabi_payments.rail.disabled import DisabledRefundRail
from sabi_payments.rail.factory import build_rail
from sabi_payments.rail.mock import MockRail, MockRefundScenario
from sabi_payments.rail.port import RailRefund, RailRefundOutcome
from sabi_payments.rail.settings import RailSettings

USER_HEADERS = {"X-Sabi-User-Id": "user-1", "X-Sabi-Payee": "Lagos State Internal Revenue"}


# --------------------------------------------------------------------------- #
# Mock rail: refund outcomes, reference keying, and duplicate blocking
# --------------------------------------------------------------------------- #
def refund(**overrides: object) -> RailRefund:
    fields: dict = {
        "payment_id": "pay-1",
        "user_id": "user-1",
        "amount": 50_000,
        "currency": "NGN",
        "reference": "SBX-CHARGE-1",
        "reason": "The payment was debited without delivery.",
        "idempotency_key": "rf-1",
    }
    fields.update(overrides)
    return RailRefund(**fields)  # type: ignore[arg-type]


def test_refund_defaults_to_a_settled_reversal_with_a_reference() -> None:
    rail = MockRail()
    outcome = rail.refund(refund())
    assert outcome.status == "reversed"
    assert outcome.refund_reference
    assert outcome.failure_reason is None
    assert rail.refunds == [refund()]


def test_a_second_refund_for_the_same_reference_is_blocked() -> None:
    rail = MockRail()
    first = rail.refund(refund())
    second = rail.refund(refund(idempotency_key="rf-2"))
    assert second.status == "duplicate"
    # The first refund's reference is echoed, and no second one is invented.
    assert second.refund_reference == first.refund_reference


def test_a_different_reference_is_refunded_on_its_own() -> None:
    rail = MockRail()
    assert rail.refund(refund(reference="SBX-CHARGE-1")).status == "reversed"
    assert rail.refund(refund(reference="SBX-CHARGE-2")).status == "reversed"


def test_a_missing_reference_falls_back_to_the_payment_id() -> None:
    rail = MockRail()
    first = rail.refund(refund(reference=None))
    second = rail.refund(refund(reference=None, idempotency_key="rf-2"))
    assert first.status in {"reversed", "refunded"}
    assert second.status == "duplicate"


def test_the_refund_reference_is_deterministic() -> None:
    first = MockRail().refund(refund())
    second = MockRail().refund(refund())
    assert first.refund_reference == second.refund_reference


def test_a_configured_refund_scenario_can_settle_as_refunded() -> None:
    rail = MockRail(default_refund_scenario=MockRefundScenario.REFUNDED)
    assert rail.refund(refund()).status == "refunded"


def test_an_enqueued_refund_scenario_overrides_one_then_falls_back() -> None:
    rail = MockRail()
    rail.enqueue_refund(MockRefundScenario.UNKNOWN)
    assert rail.refund(refund()).status == "pending"
    assert rail.refund(refund()).status == "reversed"


def test_a_declined_refund_fails_with_a_reason() -> None:
    rail = MockRail(default_refund_scenario=MockRefundScenario.DECLINE)
    outcome = rail.refund(refund())
    assert outcome.status == "failed"
    assert outcome.refund_reference is None
    assert outcome.failure_reason


def test_an_unsettled_refund_is_pending_not_settled() -> None:
    rail = MockRail(default_refund_scenario=MockRefundScenario.UNKNOWN)
    outcome = rail.refund(refund())
    assert outcome.status == "pending"
    assert outcome.refund_reference is None


# --------------------------------------------------------------------------- #
# Disabled adapter and factory selection
# --------------------------------------------------------------------------- #
def test_disabled_rail_refunds_an_unknown_outcome_and_invents_nothing() -> None:
    outcome = DisabledRefundRail().refund(refund())
    assert outcome.status == "pending"
    assert outcome.refund_reference is None


def test_disabled_refund_rail_still_is_the_disabled_charge_rail() -> None:
    # The charge boundary keeps its identity so a consumer can still recognise
    # the disabled deployment while the refund boundary is added.
    assert isinstance(DisabledRefundRail(), DisabledRail)


def test_the_factory_returns_a_refund_capable_rail() -> None:
    assert isinstance(build_rail(RailSettings(_env_file=None, environment="development")), MockRail)
    disabled = build_rail(RailSettings(_env_file=None, environment="production"))
    assert isinstance(disabled, DisabledRefundRail)


# --------------------------------------------------------------------------- #
# C-029 over HTTP
# --------------------------------------------------------------------------- #
@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = PaymentSettings(
        _env_file=None,
        payments_database_url="postgresql+psycopg://sabi:secret@localhost:5432/sabi_payments",
        mandate_signing_key="test-key",
    )
    app = create_app(settings)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.state.payment_service = PaymentService(factory, settings=settings, rail=FakeRail())
    app.state.rail_double = app.state.payment_service._rail  # noqa: SLF001 (test handle)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


def authorise_payload(**overrides: object) -> dict:
    payload: dict = {
        "serviceId": "svc-1",
        "amount": 50_000,
        "currency": "NGN",
        "payeeReference": "TIN-123",
        "paymentMethodId": None,
        "channel": "app",
        "secondConfirmation": False,
    }
    payload.update(overrides)
    return payload


def settle_payment(client: TestClient, *, headers: dict | None = None) -> str:
    owner = headers or USER_HEADERS
    authorised = client.post(
        "/v1/payments/authorise", json=authorise_payload(), headers=owner
    ).json()
    client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={**owner, "Idempotency-Key": "exec-1"},
    )
    return authorised["paymentId"]


def test_refund_returns_the_c029_body(client: TestClient) -> None:
    payment_id = settle_payment(client)
    response = client.post(
        f"/v1/payments/{payment_id}/refund",
        json={"reason": "The biller rejected the payment."},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-1"},
    )
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"paymentId", "status", "refundReference"}
    assert body["paymentId"] == payment_id
    assert body["status"] == "reversed"
    assert body["refundReference"] == "RAIL-RF-1"


def test_refund_requires_an_authenticated_owner(client: TestClient) -> None:
    response = client.post(
        "/v1/payments/missing/refund",
        json={"reason": "Refund"},
        headers={"Idempotency-Key": "refund-1"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_refund_requires_an_idempotency_key(client: TestClient) -> None:
    payment_id = settle_payment(client)
    response = client.post(
        f"/v1/payments/{payment_id}/refund",
        json={"reason": "Refund"},
        headers=USER_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_refund_unknown_payment_is_404(client: TestClient) -> None:
    response = client.post(
        "/v1/payments/missing/refund",
        json={"reason": "Refund"},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-1"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_refund_of_another_accounts_payment_is_404(client: TestClient) -> None:
    payment_id = settle_payment(client)
    response = client.post(
        f"/v1/payments/{payment_id}/refund",
        json={"reason": "Refund"},
        headers={
            "X-Sabi-User-Id": "user-2",
            "X-Sabi-Payee": "Lagos State Internal Revenue",
            "Idempotency-Key": "refund-1",
        },
    )
    assert response.status_code == 404


def test_a_second_refund_is_a_duplicate(client: TestClient) -> None:
    payment_id = settle_payment(client)
    headers = {**USER_HEADERS, "Idempotency-Key": "refund-1"}
    first = client.post(
        f"/v1/payments/{payment_id}/refund", json={"reason": "Refund"}, headers=headers
    )
    assert first.status_code == 202
    second = client.post(
        f"/v1/payments/{payment_id}/refund",
        json={"reason": "Refund"},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-2"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_an_unsettled_payment_is_not_refundable(client: TestClient) -> None:
    authorised = client.post(
        "/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS
    ).json()
    response = client.post(
        f"/v1/payments/{authorised['paymentId']}/refund",
        json={"reason": "Refund"},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-1"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_the_rail_is_not_asked_to_refund_an_unsettled_payment(client: TestClient) -> None:
    rail: FakeRail = client.app.state.rail_double  # type: ignore[attr-defined]
    authorised = client.post(
        "/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS
    ).json()
    client.post(
        f"/v1/payments/{authorised['paymentId']}/refund",
        json={"reason": "Refund"},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-1"},
    )
    assert rail.refunds == []


def test_an_unsettled_refund_is_reported_as_unavailable(client: TestClient) -> None:
    rail: FakeRail = client.app.state.rail_double  # type: ignore[attr-defined]
    rail.refund_outcome = RailRefundOutcome(status="pending")
    payment_id = settle_payment(client)
    response = client.post(
        f"/v1/payments/{payment_id}/refund",
        json={"reason": "Refund"},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-1"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payment_unavailable"


def test_a_settled_refund_advances_the_payment_state_and_event(client: TestClient) -> None:
    payment_id = settle_payment(client)
    client.post(
        f"/v1/payments/{payment_id}/refund",
        json={"reason": "The biller rejected the payment."},
        headers={**USER_HEADERS, "Idempotency-Key": "refund-1"},
    )
    listed = client.get("/v1/payments", params={"status": "reversed"}, headers=USER_HEADERS).json()
    assert [item["paymentId"] for item in listed["payments"]] == [payment_id]
