"""C-017..C-019 wire conformance: headers, status codes, and body shapes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from payment_fixtures import FakeRail
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sabi_payments.core.config import PaymentSettings
from sabi_payments.core.rail import RailOutcome
from sabi_payments.db.base import Base
from sabi_payments.main import create_app
from sabi_payments.payments.service import PaymentService

USER_HEADERS = {"X-Sabi-User-Id": "user-1", "X-Sabi-Payee": "Lagos State Internal Revenue"}


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


def test_authorise_returns_the_c017_body(client: TestClient) -> None:
    response = client.post("/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"paymentId", "status", "mandateId", "railReference"}
    assert body["status"] == "authorized"
    assert body["railReference"] is None


def test_authorise_requires_an_authenticated_owner(client: TestClient) -> None:
    response = client.post("/v1/payments/authorise", json=authorise_payload())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_authorise_above_limit_without_confirmation_is_422(client: TestClient) -> None:
    response = client.post(
        "/v1/payments/authorise",
        json=authorise_payload(amount=6_000_000),
        headers=USER_HEADERS,
    )
    assert response.status_code == 422


def test_authorise_duplicate_returns_409_with_the_existing_payment(client: TestClient) -> None:
    headers = {**USER_HEADERS, "Idempotency-Key": "key-1"}
    first = client.post("/v1/payments/authorise", json=authorise_payload(), headers=headers)
    second = client.post("/v1/payments/authorise", json=authorise_payload(), headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["details"]["paymentId"] == first.json()["paymentId"]


def test_execute_returns_the_c018_body_and_the_reference(client: TestClient) -> None:
    authorised = client.post(
        "/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS
    ).json()
    response = client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={**USER_HEADERS, "Idempotency-Key": "exec-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"paymentId", "status", "railReference"}
    assert body["status"] == "succeeded"
    assert body["railReference"] == "RAIL-1"


def test_execute_unknown_payment_is_404(client: TestClient) -> None:
    response = client.post(
        "/v1/payments/missing/execute",
        json={"mandateId": "m"},
        headers={**USER_HEADERS, "Idempotency-Key": "exec-1"},
    )
    assert response.status_code == 404


def test_execute_expired_mandate_is_410(client: TestClient) -> None:
    authorised = client.post(
        "/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS
    ).json()
    # Force expiry through the service's own store.
    service: PaymentService = client.app.state.payment_service  # type: ignore[attr-defined]
    from datetime import UTC, datetime, timedelta

    from sabi_payments.db.models import PaymentMandate

    with service._session_factory() as session:  # noqa: SLF001 (test seam)
        mandate = session.get(PaymentMandate, authorised["mandateId"])
        mandate.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    response = client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={**USER_HEADERS, "Idempotency-Key": "exec-1"},
    )
    assert response.status_code == 410


def test_list_returns_the_c019_body(client: TestClient) -> None:
    client.post("/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS)
    response = client.get("/v1/payments", headers=USER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"payments", "nextCursor"}
    assert body["nextCursor"] is None
    summary = body["payments"][0]
    assert set(summary) == {
        "paymentId",
        "serviceId",
        "amount",
        "currency",
        "payee",
        "status",
        "channel",
        "createdAt",
        "updatedAt",
    }
    assert summary["payee"] == "Lagos State Internal Revenue"


def test_list_rejects_an_unknown_status(client: TestClient) -> None:
    response = client.get("/v1/payments", params={"status": "bogus"}, headers=USER_HEADERS)
    assert response.status_code == 400


def test_rail_failure_is_reported_as_failed(client: TestClient) -> None:
    service: PaymentService = client.app.state.payment_service  # type: ignore[attr-defined]
    service._rail.outcome = RailOutcome(  # noqa: SLF001 (test handle)
        status="failed", failure_reason="Biller rejected the payment."
    )
    authorised = client.post(
        "/v1/payments/authorise", json=authorise_payload(), headers=USER_HEADERS
    ).json()
    response = client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={**USER_HEADERS, "Idempotency-Key": "exec-1"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
