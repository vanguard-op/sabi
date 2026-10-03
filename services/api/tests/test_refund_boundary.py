"""The gateway's C-029 refund boundary to the isolated payment module (FEAT-009).

The case workflow resolves ``app.state.cases_refund_port``; before this boundary
was bound it fell back to the refusing default and a client refund returned 503.
These tests pin the three outcomes the route names: a settled refund the module
accepts, a duplicate the module refuses with its shared 409 envelope, and an
unreachable module. The adapter is exercised directly and the whole C-029 route
is driven through the real :class:`HttpPaymentModuleClient` with a stubbed
transport, so the owner header and the idempotency key are seen on the wire.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import make_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import InMemoryAuditLog
from app.core.errors import APIError, ErrorCode
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import InMemorySessionStore, SessionManager
from app.db.base import Base
from app.main import create_app
from app.payments.client import (
    PAYMENT_UNAVAILABLE,
    ForwardContext,
    HttpPaymentModuleClient,
    HttpPaymentModuleRefundPort,
    PaymentEndpoint,
    PaymentModuleUnavailable,
)
from app.payments_port import InMemoryPaymentLookup, PaymentView

_OWNER = "user-1"
_PAYMENT_ID = "pay-1"
_BASE_TIME = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)

_REFUND_RESPONSE = {
    "paymentId": _PAYMENT_ID,
    "status": "reversed",
    "refundReference": "rail-refund-1",
}
_DUPLICATE_ENVELOPE = {
    "error": {
        "code": "conflict",
        "message": "A refund for this payment has already been requested.",
    }
}


class _ModuleTransport(httpx.BaseTransport):
    """A stub for the payment module hop that records the forwarded request."""

    def __init__(self, response: httpx.Response | None, *, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _client_with(transport: _ModuleTransport) -> HttpPaymentModuleClient:
    client = HttpPaymentModuleClient(PaymentEndpoint("http://payments.invalid", 1.0))
    client._client = httpx.Client(  # type: ignore[assignment]
        base_url="http://payments.invalid", transport=transport
    )
    return client


def _response(status: int, json: Any) -> httpx.Response:
    return httpx.Response(status, json=json, request=httpx.Request("POST", "http://payments/v1"))


# --------------------------------------------------------------------------- #
# The adapter the case workflow consumes
# --------------------------------------------------------------------------- #
def test_adapter_maps_a_settled_refund_to_a_refund_view() -> None:
    transport = _ModuleTransport(_response(202, _REFUND_RESPONSE))
    port = HttpPaymentModuleRefundPort(_client_with(transport))

    result = port.refund(
        user_id=_OWNER,
        payment_id=_PAYMENT_ID,
        reason="Debited without delivery.",
        idempotency_key="rf-1",
    )

    assert result.status == "reversed"
    assert result.refund_reference == "rail-refund-1"
    request = transport.requests[0]
    assert str(request.url) == "http://payments.invalid/v1/payments/pay-1/refund"
    headers = {key.lower(): value for key, value in request.headers.items()}
    assert headers["x-sabi-user-id"] == _OWNER
    assert headers["idempotency-key"] == "rf-1"
    assert request.content == b'{"reason":"Debited without delivery."}'


def test_adapter_re_raises_the_modules_duplicate_envelope() -> None:
    transport = _ModuleTransport(_response(409, _DUPLICATE_ENVELOPE))
    port = HttpPaymentModuleRefundPort(_client_with(transport))

    with pytest.raises(APIError) as error:
        port.refund(
            user_id=_OWNER,
            payment_id=_PAYMENT_ID,
            reason="Refund again.",
            idempotency_key="rf-2",
        )

    assert error.value.status_code == 409
    assert error.value.code == ErrorCode.CONFLICT
    assert error.value.message == "A refund for this payment has already been requested."


def test_adapter_reports_an_unreachable_module_as_unavailable() -> None:
    transport = _ModuleTransport(
        None, error=httpx.ConnectError("boom", request=httpx.Request("POST", "http://payments/v1"))
    )
    port = HttpPaymentModuleRefundPort(_client_with(transport))

    with pytest.raises(APIError) as error:
        port.refund(
            user_id=_OWNER,
            payment_id=_PAYMENT_ID,
            reason="Refund.",
            idempotency_key="rf-3",
        )

    assert error.value.status_code == 503
    assert error.value.code == PAYMENT_UNAVAILABLE


def test_adapter_refuses_a_payload_without_a_status() -> None:
    # A module that answers 2xx but omits the status must not be read as settled.
    transport = _ModuleTransport(_response(202, {"paymentId": _PAYMENT_ID}))
    port = HttpPaymentModuleRefundPort(_client_with(transport))

    with pytest.raises(PaymentModuleUnavailable):
        port.refund(
            user_id=_OWNER,
            payment_id=_PAYMENT_ID,
            reason="Refund.",
            idempotency_key="rf-4",
        )


def test_adapter_forwards_an_empty_reference_as_none() -> None:
    transport = _ModuleTransport(
        _response(202, {"paymentId": _PAYMENT_ID, "status": "refunded", "refundReference": None})
    )
    port = HttpPaymentModuleRefundPort(_client_with(transport))

    result = port.refund(
        user_id=_OWNER,
        payment_id=_PAYMENT_ID,
        reason="Refund.",
        idempotency_key="rf-5",
    )

    assert result.status == "refunded"
    assert result.refund_reference is None


def test_context_carries_only_the_owner_for_a_refund() -> None:
    client = _client_with(_ModuleTransport(_response(202, _REFUND_RESPONSE)))
    assert client._headers(ForwardContext(user_id=_OWNER)) == {"X-Sabi-User-Id": _OWNER}


# --------------------------------------------------------------------------- #
# The bound C-029 route, end to end
# --------------------------------------------------------------------------- #
@pytest.fixture
def db_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


def _app_with_transport(
    db_factory: sessionmaker[Session], transport: _ModuleTransport
) -> tuple[FastAPI, SessionManager, TestClient]:
    settings = make_settings()
    session_manager = SessionManager(settings, InMemorySessionStore())
    application = create_app(settings)
    application.state.session_factory = db_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1000, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()

    application.state.cases_payment_lookup = InMemoryPaymentLookup(
        [
            PaymentView(
                payment_id=_PAYMENT_ID,
                user_id=_OWNER,
                service_id="svc-1",
                reference="rail-1",
                payee="Onitsha South LGA",
                amount=500_000,
                currency="NGN",
                status="succeeded",
                channel="app",
                created_at=_BASE_TIME,
                updated_at=_BASE_TIME,
            )
        ]
    )

    # Swap the hop's transport but keep the client the factory bound, so the
    # route still resolves through the real refund port.
    client = application.state.payment_module_client
    client._client = httpx.Client(  # type: ignore[attr-defined, assignment]
        base_url="http://payments.invalid", transport=transport
    )
    return application, session_manager, TestClient(application)


def _sign_in(client: TestClient, manager: SessionManager, user_id: str = _OWNER) -> None:
    token, _ = manager.issue(user_id=user_id)
    client.cookies.set(manager.settings.session_cookie_name, token)


def test_create_app_binds_the_refund_port_to_the_payment_module(
    db_factory: sessionmaker[Session],
) -> None:
    application, _, _ = _app_with_transport(db_factory, _ModuleTransport(None))
    assert isinstance(application.state.cases_refund_port, HttpPaymentModuleRefundPort)


def test_refund_route_returns_the_module_body(db_factory: sessionmaker[Session]) -> None:
    _, manager, client = _app_with_transport(
        db_factory, _ModuleTransport(_response(202, _REFUND_RESPONSE))
    )
    with client:
        _sign_in(client, manager)
        response = client.post(
            f"/v1/payments/{_PAYMENT_ID}/refund",
            json={"reason": "Debited without delivery."},
            headers={"Idempotency-Key": "rf-1"},
        )

    assert response.status_code == 202
    assert response.json() == _REFUND_RESPONSE


def test_refund_route_forwards_the_duplicate_409_verbatim(
    db_factory: sessionmaker[Session],
) -> None:
    _, manager, client = _app_with_transport(
        db_factory, _ModuleTransport(_response(409, _DUPLICATE_ENVELOPE))
    )
    with client:
        _sign_in(client, manager)
        response = client.post(
            f"/v1/payments/{_PAYMENT_ID}/refund",
            json={"reason": "Refund again."},
            headers={"Idempotency-Key": "rf-2"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert (
        response.json()["error"]["message"]
        == "A refund for this payment has already been requested."
    )


def test_refund_route_maps_an_unreachable_module_to_503(
    db_factory: sessionmaker[Session],
) -> None:
    _, manager, client = _app_with_transport(
        db_factory,
        _ModuleTransport(
            None,
            error=httpx.ConnectError("boom", request=httpx.Request("POST", "http://payments/v1")),
        ),
    )
    with client:
        _sign_in(client, manager)
        response = client.post(
            f"/v1/payments/{_PAYMENT_ID}/refund",
            json={"reason": "Refund."},
            headers={"Idempotency-Key": "rf-3"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == PAYMENT_UNAVAILABLE
