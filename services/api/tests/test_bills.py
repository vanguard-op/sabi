"""Everyday bill flow unit tests (FEAT-007, C-033–C-035).

Covers the validate/pay/token contract shapes and status codes, the biller
offline and insufficient-funds failure paths, duplicate-authorisation idempotency,
token capture and awaiting-token retrieval, owner scoping, and the unauthenticated
and unwired-boundary behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.bills.ports import (
    BillAmountRange,
    BillPaymentResult,
    InMemoryBillerPort,
    InMemoryBillPaymentPort,
)
from app.bills.router import router as bills_router
from app.core.errors import APIError
from app.core.ids import new_id
from app.db.models import Receipt, Service
from app.payments_port import InMemoryPaymentLookup, PaymentView

FIXED_NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def _mounted(app) -> bool:
    return any(path.startswith("/v1/payments/bills") for path in app.openapi().get("paths", {}))


def _payment(
    *,
    payment_id: str | None = None,
    user_id: str = "user-1",
    service_id: str = "service-1",
) -> PaymentView:
    return PaymentView(
        payment_id=payment_id or new_id(),
        user_id=user_id,
        service_id=service_id,
        reference="RAIL-1",
        payee="Eko Electricity",
        amount=5_000,
        currency="NGN",
        status="succeeded",
        channel="app",
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


@pytest.fixture
def bills(app, client, db_session_factory, session_manager):
    """A client backed by isolated SQLite, in-memory boundaries, and sign-in."""
    app.state.session_factory = db_session_factory
    biller = InMemoryBillerPort()
    payments = InMemoryBillPaymentPort()
    lookup = InMemoryPaymentLookup()
    app.state.bills_biller = biller
    app.state.bills_payments = payments
    app.state.bills_payment_lookup = lookup

    if not _mounted(app):
        app.include_router(bills_router, prefix="/v1")

    with db_session_factory() as db:
        db.add(
            Service(
                id="service-1",
                type="biller",
                name="Eko Electricity",
                collecting_body="Eko Electricity",
                category="electricity",
                aliases=[],
                known_amount=None,
                currency="NGN",
                status="active",
            )
        )
        db.commit()

    def sign_in(user_id: str = "user-1") -> None:
        token, _ = session_manager.issue(user_id=user_id)
        client.cookies.set(session_manager.settings.session_cookie_name, token)

    return SimpleNamespace(
        client=client,
        biller=biller,
        payments=payments,
        lookup=lookup,
        sign_in=sign_in,
        db_session_factory=db_session_factory,
    )


# --- C-033: validate -------------------------------------------------------


def test_validate_requires_a_session(bills) -> None:
    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_validate_accepts_a_registered_recipient(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890", known_amount=5_000)
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "valid": True,
        "recipientIdentifier": "1234567890",
        "knownAmount": 5_000,
        "currency": "NGN",
        "range": None,
        "reason": None,
    }


def test_validate_reports_an_unknown_recipient_without_erroring(bills) -> None:
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "0000000000"},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["reason"]
    assert response.json()["knownAmount"] is None


def test_validate_reports_a_variable_bill_range(bills) -> None:
    bills.biller.register(
        service_id="service-1",
        recipient="1234567890",
        amount_range=BillAmountRange(minimum=1_000, maximum=50_000),
    )
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
    )

    assert response.status_code == 200
    assert response.json()["range"] == {"minimum": 1_000, "maximum": 50_000}


def test_validate_rejects_an_amount_outside_the_biller_range(bills) -> None:
    bills.biller.register(
        service_id="service-1",
        recipient="1234567890",
        amount_range=BillAmountRange(minimum=1_000, maximum=5_000),
    )
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 50_000},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["reason"]


def test_validate_unknown_service_is_404(bills) -> None:
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "does-not-exist", "recipientIdentifier": "1234567890"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_validate_offline_biller_is_503(bills) -> None:
    bills.biller.set_offline(True)
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "biller_unavailable"


def test_validate_blank_identifier_is_400(bills) -> None:
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": "service-1", "recipientIdentifier": "   "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


# --- C-034: pay ------------------------------------------------------------


def test_pay_requires_a_session(bills) -> None:
    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
    )
    assert response.status_code == 401


def test_pay_requires_an_idempotency_key(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890")
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_pay_returns_the_token_and_stores_it_with_the_receipt(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890")
    bills.payments.set_result(
        BillPaymentResult(payment_id="payment-1", status="succeeded", token="TOKEN-ABC")
    )
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
        headers={"Idempotency-Key": "key-1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["paymentId"] == "payment-1"
    assert body["status"] == "succeeded"
    assert body["token"] == "TOKEN-ABC"
    assert body["receiptId"]

    with bills.db_session_factory() as db:
        receipt = db.get(Receipt, body["receiptId"])
        assert receipt is not None
        assert receipt.kind == "token"
        assert receipt.document_ref == "TOKEN-ABC"
        assert receipt.payment_id == "payment-1"

    call = bills.payments.calls[-1]
    assert call["recipient"] == "1234567890"
    assert call["amount"] == 5_000
    assert call["payee"] == "Eko Electricity"


def test_pay_captures_a_biller_confirmation_for_a_non_token_bill(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890")
    bills.payments.set_result(
        BillPaymentResult(payment_id="payment-2", status="succeeded", reference="RAIL-9")
    )
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 2_000},
        headers={"Idempotency-Key": "key-2"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token"] is None
    assert body["receiptId"]

    with bills.db_session_factory() as db:
        receipt = db.get(Receipt, body["receiptId"])
        assert receipt.kind == "biller_confirmation"
        assert receipt.document_ref == "RAIL-9"


def test_pay_duplicate_authorisation_is_409(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890")
    bills.payments.duplicate_error = APIError(
        409, "conflict", "This authorisation was already received."
    )
    bills.sign_in()

    payload = {
        "serviceId": "service-1",
        "recipientIdentifier": "1234567890",
        "amount": 5_000,
    }
    first = bills.client.post(
        "/v1/payments/bills", json=payload, headers={"Idempotency-Key": "same-key"}
    )
    second = bills.client.post(
        "/v1/payments/bills", json=payload, headers={"Idempotency-Key": "same-key"}
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_pay_insufficient_funds_is_402(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890")
    bills.payments.failure_error = APIError(
        402, "insufficient_funds", "Your account cannot cover this payment."
    )
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
        headers={"Idempotency-Key": "key-3"},
    )

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "insufficient_funds"


def test_pay_offline_biller_is_503_and_prevents_payment(bills) -> None:
    bills.biller.set_offline(True)
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
        headers={"Idempotency-Key": "key-4"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "biller_unavailable"
    # No debit: the payment module was never asked.
    assert bills.payments.calls == []


def test_pay_rejects_an_invalid_recipient_before_the_rail(bills) -> None:
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "0000000000", "amount": 5_000},
        headers={"Idempotency-Key": "key-5"},
    )

    assert response.status_code == 400
    assert bills.payments.calls == []


def test_pay_unknown_service_is_400(bills) -> None:
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={"serviceId": "nope", "recipientIdentifier": "1234567890", "amount": 5_000},
        headers={"Idempotency-Key": "key-6"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_pay_rejects_a_non_naira_currency(bills) -> None:
    bills.biller.register(service_id="service-1", recipient="1234567890")
    bills.sign_in()

    response = bills.client.post(
        "/v1/payments/bills",
        json={
            "serviceId": "service-1",
            "recipientIdentifier": "1234567890",
            "amount": 5_000,
            "currency": "USD",
        },
        headers={"Idempotency-Key": "key-7"},
    )

    assert response.status_code == 400


def test_pay_reports_payment_unavailable_when_the_module_is_not_wired(
    app, client, session_manager, db_session_factory
) -> None:
    app.state.session_factory = db_session_factory
    app.state.bills_biller = InMemoryBillerPort()
    app.state.bills_biller.register(service_id="service-1", recipient="1234567890")
    # No bills_payments bound: the default refuses.
    if not _mounted(app):
        app.include_router(bills_router, prefix="/v1")
    with db_session_factory() as db:
        db.add(
            Service(
                id="service-1",
                type="biller",
                name="Eko Electricity",
                collecting_body="Eko Electricity",
                category="electricity",
                aliases=[],
                currency="NGN",
                status="active",
            )
        )
        db.commit()
    token, _ = session_manager.issue(user_id="user-1")
    client.cookies.set(session_manager.settings.session_cookie_name, token)

    response = client.post(
        "/v1/payments/bills",
        json={"serviceId": "service-1", "recipientIdentifier": "1234567890", "amount": 5_000},
        headers={"Idempotency-Key": "key-8"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payment_unavailable"


# --- C-035: token ----------------------------------------------------------


def test_token_requires_a_session(bills) -> None:
    payment = _payment()
    bills.lookup.add(payment)
    response = bills.client.get(f"/v1/payments/bills/{payment.payment_id}/token")
    assert response.status_code == 401


def test_token_returns_the_stored_token(bills) -> None:
    payment = _payment()
    bills.lookup.add(payment)
    with bills.db_session_factory() as db:
        db.add(
            Receipt(
                id=new_id(),
                payment_id=payment.payment_id,
                user_id="user-1",
                kind="token",
                document_ref="TOKEN-XYZ",
                verification_status="verified",
            )
        )
        db.commit()
    bills.sign_in()

    response = bills.client.get(f"/v1/payments/bills/{payment.payment_id}/token")

    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "TOKEN-XYZ"
    assert body["receiptId"]


def test_token_awaiting_retrieval_is_202(bills) -> None:
    payment = _payment()
    bills.lookup.add(payment)
    bills.sign_in()

    response = bills.client.get(f"/v1/payments/bills/{payment.payment_id}/token")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "awaiting_token"
    assert body["retryAfterSeconds"] >= 1
    assert "token" not in body


def test_token_unknown_payment_is_404(bills) -> None:
    bills.sign_in()
    response = bills.client.get("/v1/payments/bills/nope/token")
    assert response.status_code == 404


def test_token_of_another_users_payment_is_404(bills) -> None:
    payment = _payment(user_id="user-2")
    bills.lookup.add(payment)
    bills.sign_in("user-1")

    response = bills.client.get(f"/v1/payments/bills/{payment.payment_id}/token")

    assert response.status_code == 404


def test_token_reports_payment_unavailable_when_the_store_is_not_wired(
    app, client, session_manager, db_session_factory
) -> None:
    app.state.session_factory = db_session_factory
    if not _mounted(app):
        app.include_router(bills_router, prefix="/v1")
    token, _ = session_manager.issue(user_id="user-1")
    client.cookies.set(session_manager.settings.session_cookie_name, token)

    response = client.get("/v1/payments/bills/anything/token")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payment_unavailable"


# --- mount -----------------------------------------------------------------


def test_bills_paths_are_mounted_under_v1(app) -> None:
    paths = app.openapi().get("paths", {})
    assert "/v1/payments/bills/validate" in paths
    assert "/v1/payments/bills" in paths
    assert "/v1/payments/bills/{paymentId}/token" in paths
