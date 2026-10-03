"""Unit tests for the gateway payment module (C-017..C-019; FEAT-005).

They exercise what the gateway owns: the authenticated account-owner gate, rate
limiting, the contract's request bounds, the resolution of a service to its
collecting body, the pass-through of the payment module's body, and the mapping
of an upstream refusal and an unreachable module. Authorisation, mandates, the
rail, and the payment store are covered by the payment module's own tests, not
here.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.audit import InMemoryAuditLog
from app.core.config import Settings
from app.core.errors import APIError, register_exception_handlers
from app.core.ids import new_id
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import SessionKind, SessionManager
from app.db.models import Service
from app.db.session import get_db
from app.payments.client import (
    PAYMENT_UNAVAILABLE,
    ForwardContext,
    HttpPaymentModuleClient,
    PaymentEndpoint,
    PaymentModuleClient,
    PaymentModuleUnavailable,
    _upstream_error,
)
from app.payments.deps import get_payment_client
from app.payments.router import router as payments_router

AUTHORISE_RESPONSE = {
    "paymentId": "payment-1",
    "status": "authorized",
    "mandateId": "mandate-1",
    "railReference": None,
}
EXECUTE_RESPONSE = {
    "paymentId": "payment-1",
    "status": "succeeded",
    "railReference": "RAIL-1",
}
LIST_RESPONSE = {
    "payments": [
        {
            "paymentId": "payment-1",
            "serviceId": "service-1",
            "amount": 5_000,
            "currency": "NGN",
            "payee": "Eko Electricity",
            "status": "succeeded",
            "channel": "app",
            "createdAt": "2026-03-01T09:00:00Z",
            "updatedAt": "2026-03-01T09:00:01Z",
        }
    ],
    "nextCursor": None,
}


class FakePaymentClient:
    """A deterministic stand-in for the payment module client."""

    def __init__(self) -> None:
        self.authorise_calls: list[dict[str, Any]] = []
        self.execute_calls: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []
        self.error: APIError | None = None
        self.authorise_response: dict[str, Any] = AUTHORISE_RESPONSE
        self.execute_response: dict[str, Any] = EXECUTE_RESPONSE
        self.list_response: dict[str, Any] = LIST_RESPONSE

    def authorise(
        self, *, context: ForwardContext, body: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        self.authorise_calls.append(
            {"context": context, "body": body, "idempotency_key": idempotency_key}
        )
        if self.error is not None:
            raise self.error
        return self.authorise_response

    def execute(
        self,
        *,
        context: ForwardContext,
        payment_id: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.execute_calls.append(
            {
                "context": context,
                "payment_id": payment_id,
                "body": body,
                "idempotency_key": idempotency_key,
            }
        )
        if self.error is not None:
            raise self.error
        return self.execute_response

    def list_payments(
        self, *, context: ForwardContext, cursor: str | None, limit: int, status: str | None
    ) -> dict[str, Any]:
        self.list_calls.append(
            {"context": context, "cursor": cursor, "limit": limit, "status": status}
        )
        if self.error is not None:
            raise self.error
        return self.list_response


@pytest.fixture
def payment_client() -> FakePaymentClient:
    return FakePaymentClient()


@pytest.fixture
def app(
    settings: Settings,
    session_manager: SessionManager,
    payment_client: FakePaymentClient,
    db_session_factory: sessionmaker,
) -> FastAPI:
    application = FastAPI()
    application.state.settings = settings
    application.state.session_factory = db_session_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1000, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    application.state.payment_module_client = payment_client
    application.dependency_overrides[get_payment_client] = lambda: payment_client

    def _seeded_db(request: Request) -> Iterator[Session]:
        factory: sessionmaker = request.app.state.session_factory
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    application.dependency_overrides[get_db] = _seeded_db
    register_exception_handlers(application)
    application.include_router(payments_router, prefix="/v1")
    return application


@pytest.fixture
def api_client(app: FastAPI, db_session_factory: sessionmaker) -> Iterator[TestClient]:
    with db_session_factory() as db:
        db.add(
            Service(
                id="service-1",
                type="government",
                name="Land Use Charge",
                collecting_body="Lagos State Land Bureau",
                category="government",
                aliases=[],
                known_amount=None,
                currency="NGN",
            )
        )
        db.add(
            Service(
                id="service-no-payee",
                type="biller",
                name="Nameless",
                collecting_body="   ",
                category="other",
                aliases=[],
                known_amount=None,
                currency="NGN",
            )
        )
        db.commit()
    with TestClient(app) as client:
        yield client


def _sign_in(client: TestClient, manager: SessionManager, *, kind: SessionKind = SessionKind.USER):
    token, _ = manager.issue(user_id=new_id(), kind=kind)
    client.cookies.set(manager.settings.session_cookie_name, token)


def _authorise_body(**overrides: Any) -> dict[str, Any]:
    body = {"serviceId": "service-1", "amount": 5_000, "currency": "NGN", "channel": "app"}
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# C-017 authorisation
# --------------------------------------------------------------------------- #
def test_authorise_requires_a_session(api_client: TestClient) -> None:
    response = api_client.post("/v1/payments/authorise", json=_authorise_body())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_authorise_resolves_and_forwards_the_trusted_context(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/payments/authorise", json=_authorise_body())
    assert response.status_code == 201
    assert response.json() == AUTHORISE_RESPONSE
    assert len(payment_client.authorise_calls) == 1
    call = payment_client.authorise_calls[0]
    assert call["context"].payee == "Lagos State Land Bureau"
    assert call["context"].service_type == "government"
    assert call["context"].user_id
    assert call["body"] == {
        "serviceId": "service-1",
        "amount": 5_000,
        "currency": "NGN",
        "payeeReference": None,
        "paymentMethodId": None,
        "channel": "app",
        "secondConfirmation": False,
    }


def test_authorise_forwards_the_idempotency_key(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    api_client.post(
        "/v1/payments/authorise",
        json=_authorise_body(secondConfirmation=True),
        headers={"Idempotency-Key": "key-1"},
    )
    assert payment_client.authorise_calls[0]["idempotency_key"] == "key-1"
    assert payment_client.authorise_calls[0]["body"]["secondConfirmation"] is True


@pytest.mark.parametrize(
    "body",
    [
        _authorise_body(amount=0),
        _authorise_body(amount=-5),
        _authorise_body(currency="USD"),
        _authorise_body(channel="email"),
        _authorise_body(serviceId=""),
        _authorise_body(serviceId="missing-service"),
        _authorise_body(serviceId="service-no-payee"),
    ],
)
def test_authorise_rejects_out_of_contract_input_with_400(
    api_client: TestClient,
    session_manager: SessionManager,
    payment_client: FakePaymentClient,
    body: dict,
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/payments/authorise", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert payment_client.authorise_calls == []


def test_authorise_rejects_a_missing_amount_with_422(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    # The schema layer reports a wrong type; the router's contract 400 covers
    # values that pass the schema but fail the business rule.
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/payments/authorise", json={"serviceId": "service-1"})
    assert response.status_code == 422
    assert payment_client.authorise_calls == []


def test_authorise_forwards_a_duplicate_conflict_with_its_details(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    payment_client.error = APIError(
        409,
        "conflict",
        "This authorisation was already received.",
        details={"paymentId": "existing-1", "railReference": "RAIL-9"},
    )
    response = api_client.post("/v1/payments/authorise", json=_authorise_body())
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "conflict"
    assert body["details"] == {"paymentId": "existing-1", "railReference": "RAIL-9"}


def test_authorise_maps_an_unreachable_module_to_503(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    payment_client.error = PaymentModuleUnavailable()
    response = api_client.post("/v1/payments/authorise", json=_authorise_body())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == PAYMENT_UNAVAILABLE


def test_authorise_is_rate_limited(
    app: FastAPI, api_client: TestClient, session_manager: SessionManager
) -> None:
    app.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1, default_window_seconds=60
    )
    _sign_in(api_client, session_manager)
    assert api_client.post("/v1/payments/authorise", json=_authorise_body()).status_code == 201
    response = api_client.post("/v1/payments/authorise", json=_authorise_body())
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


# --------------------------------------------------------------------------- #
# C-018 execution
# --------------------------------------------------------------------------- #
def test_execute_requires_a_session(api_client: TestClient) -> None:
    response = api_client.post("/v1/payments/p1/execute", json={"mandateId": "m1"})
    assert response.status_code == 401


def test_execute_forwards_the_mandate_and_key(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post(
        "/v1/payments/p1/execute",
        json={"mandateId": "m1"},
        headers={"Idempotency-Key": "exec-1"},
    )
    assert response.status_code == 200
    assert response.json() == EXECUTE_RESPONSE
    call = payment_client.execute_calls[0]
    assert call["payment_id"] == "p1"
    assert call["body"] == {"mandateId": "m1"}
    assert call["idempotency_key"] == "exec-1"
    assert call["context"].user_id


@pytest.mark.parametrize("mandate", [None, "", "   "])
def test_execute_rejects_a_missing_mandate_with_400(
    api_client: TestClient,
    session_manager: SessionManager,
    payment_client: FakePaymentClient,
    mandate,
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post(
        "/v1/payments/p1/execute",
        json={"mandateId": mandate},
        headers={"Idempotency-Key": "exec-1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert payment_client.execute_calls == []


def test_execute_requires_an_idempotency_key(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/payments/p1/execute", json={"mandateId": "m1"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert payment_client.execute_calls == []


# --------------------------------------------------------------------------- #
# C-019 listing
# --------------------------------------------------------------------------- #
def test_list_requires_a_session(api_client: TestClient) -> None:
    response = api_client.get("/v1/payments")
    assert response.status_code == 401


def test_list_forwards_query_and_returns_the_module_body(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.get(
        "/v1/payments", params={"cursor": "c1", "limit": 5, "status": "succeeded"}
    )
    assert response.status_code == 200
    assert response.json() == LIST_RESPONSE
    call = payment_client.list_calls[0]
    assert call["cursor"] == "c1"
    assert call["limit"] == 5
    assert call["status"] == "succeeded"
    assert call["context"].user_id


def test_list_clamps_the_limit_to_the_contract_maximum(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    api_client.get("/v1/payments", params={"limit": 5000})
    assert payment_client.list_calls[0]["limit"] == 100


def test_list_defaults_the_limit_to_twenty(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    api_client.get("/v1/payments")
    assert payment_client.list_calls[0]["limit"] == 20


def test_list_rejects_an_unknown_status_with_400(
    api_client: TestClient, session_manager: SessionManager, payment_client: FakePaymentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.get("/v1/payments", params={"status": "settled"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert payment_client.list_calls == []


def test_list_is_rate_limited(
    app: FastAPI, api_client: TestClient, session_manager: SessionManager
) -> None:
    app.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1, default_window_seconds=60
    )
    _sign_in(api_client, session_manager)
    assert api_client.get("/v1/payments").status_code == 200
    response = api_client.get("/v1/payments")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


# --------------------------------------------------------------------------- #
# Client transport mapping
# --------------------------------------------------------------------------- #
def _response(status: int, json: Any | None = None, headers: dict | None = None) -> httpx.Response:
    kwargs: dict = {"headers": headers or {}}
    if json is not None:
        kwargs["json"] = json
    return httpx.Response(status, request=httpx.Request("POST", "http://payments/v1"), **kwargs)


def test_upstream_error_forwards_code_message_and_details() -> None:
    error = _upstream_error(
        _response(
            409,
            {
                "error": {
                    "code": "conflict",
                    "message": "Already received.",
                    "details": {"paymentId": "p1"},
                }
            },
        )
    )
    assert error.status_code == 409
    assert error.code == "conflict"
    assert error.message == "Already received."
    assert error.details == {"paymentId": "p1"}


def test_upstream_error_with_an_unexpected_body_is_still_enveloped() -> None:
    error = _upstream_error(_response(402))
    assert error.status_code == 402
    assert error.code == "invalid_request"


def test_http_client_reports_a_transport_failure_as_unavailable() -> None:
    class _Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

    endpoint = PaymentEndpoint(base_url="http://payments.invalid", timeout_seconds=1.0)
    client = HttpPaymentModuleClient(endpoint)
    client._client = httpx.Client(  # type: ignore[assignment]
        base_url=endpoint.base_url, transport=_Transport()
    )
    with pytest.raises(APIError) as error:
        client.authorise(
            context=ForwardContext(user_id="u1", payee="Body", service_type="bill"),
            body={},
            idempotency_key=None,
        )
    assert error.value.status_code == 503
    assert error.value.code == PAYMENT_UNAVAILABLE


def test_endpoint_prefers_the_configured_base_url() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        session_secret="s",
        recovery_code_pepper="p",
        payments_base_url="http://payments.internal:9001/",
        payments_request_timeout_seconds=3.0,
    )
    endpoint = PaymentEndpoint.from_settings(settings)
    assert endpoint.base_url == "http://payments.internal:9001"
    assert endpoint.timeout_seconds == 3.0


def test_protocol_is_satisfied_by_the_http_client() -> None:
    assert isinstance(
        HttpPaymentModuleClient(PaymentEndpoint("http://payments", 1.0)), PaymentModuleClient
    )


def test_forward_context_omits_the_payee_for_an_owner_scoped_call() -> None:
    client = HttpPaymentModuleClient(PaymentEndpoint("http://payments", 1.0))
    headers = client._headers(ForwardContext(user_id="u1"))
    assert headers == {"X-Sabi-User-Id": "u1"}


def test_http_client_forwards_trusted_headers_and_the_key() -> None:
    captured: dict[str, Any] = {}

    class _Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["body"] = request.content.decode()
            return httpx.Response(201, json=AUTHORISE_RESPONSE, request=request)

    endpoint = PaymentEndpoint(base_url="http://payments.invalid", timeout_seconds=1.0)
    client = HttpPaymentModuleClient(endpoint)
    client._client = httpx.Client(  # type: ignore[assignment]
        base_url=endpoint.base_url, transport=_Transport()
    )
    client.authorise(
        context=ForwardContext(
            user_id="u1",
            payee="Lagos State Land Bureau",
            service_type="government",
            authorisation_limit=2_000_000,
        ),
        body={"serviceId": "service-1"},
        idempotency_key="key-1",
    )
    assert captured["url"] == "http://payments.invalid/v1/payments/authorise"
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["x-sabi-user-id"] == "u1"
    assert headers["x-sabi-payee"] == "Lagos State Land Bureau"
    assert headers["x-sabi-service-type"] == "government"
    assert headers["x-sabi-authorisation-limit"] == "2000000"
    assert headers["idempotency-key"] == "key-1"
