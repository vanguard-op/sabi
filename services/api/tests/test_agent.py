"""Unit tests for the gateway agent module (C-009, C-012).

They exercise what the gateway owns: the authenticated account-owner gate, rate
limiting, the contract's request bounds, the pass-through of the AI service body,
and the mapping of an upstream 4xx and an unreachable service. The model-backed
behaviour itself is covered by the AI service's own tests, not here.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.agent.client import (
    AI_UNAVAILABLE,
    AgentAIClient,
    AIEndpoint,
    AIUnavailable,
    HttpAgentAIClient,
    _upstream_error,
)
from app.agent.deps import get_agent_client
from app.agent.router import router as agent_router
from app.core.audit import InMemoryAuditLog
from app.core.config import Settings
from app.core.errors import APIError, register_exception_handlers
from app.core.ids import new_id
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import SessionKind, SessionManager

INTENT_BODY = {
    "intentType": "bill_payment",
    "target": None,
    "amount": None,
    "currency": "NGN",
    "reference": None,
    "constraints": {},
    "confidence": 0.9,
    "language": "en",
    "clarifyingQuestion": None,
}

INTENT_RESPONSE = {
    "intent": INTENT_BODY,
    "candidates": [],
    "source": "model",
}

SURFACE_RESPONSE = {
    "messages": [{"type": "createSurface", "surfaceId": "s1"}],
    "fallback": "confirmation",
}


class FakeAgentClient:
    """A deterministic stand-in for the AI service client."""

    def __init__(self) -> None:
        self.intent_calls: list[dict[str, Any]] = []
        self.surface_calls: list[dict[str, Any]] = []
        self.intent_error: APIError | None = None
        self.surface_error: APIError | None = None
        self.intent_response: dict[str, Any] = INTENT_RESPONSE
        self.surface_response: dict[str, Any] = SURFACE_RESPONSE

    def resolve_intent(self, *, text: str, locale: str, channel: str) -> dict[str, Any]:
        self.intent_calls.append({"text": text, "locale": locale, "channel": channel})
        if self.intent_error is not None:
            raise self.intent_error
        return self.intent_response

    def compose_surface(self, *, task: str, context: dict[str, Any]) -> dict[str, Any]:
        self.surface_calls.append({"task": task, "context": context})
        if self.surface_error is not None:
            raise self.surface_error
        return self.surface_response


@pytest.fixture
def agent_client() -> FakeAgentClient:
    return FakeAgentClient()


@pytest.fixture
def app(
    settings: Settings,
    session_manager: SessionManager,
    agent_client: FakeAgentClient,
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
    application.state.agent_ai_client = agent_client
    application.dependency_overrides[get_agent_client] = lambda: agent_client
    register_exception_handlers(application)
    application.include_router(agent_router, prefix="/v1")
    return application


@pytest.fixture
def api_client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def _sign_in(client: TestClient, manager: SessionManager, *, kind: SessionKind = SessionKind.USER):
    token, _ = manager.issue(user_id=new_id(), kind=kind)
    client.cookies.set(manager.settings.session_cookie_name, token)


# --------------------------------------------------------------------------- #
# C-009 intent resolution
# --------------------------------------------------------------------------- #
def test_intents_requires_a_session(api_client: TestClient) -> None:
    response = api_client.post("/v1/agent/intents", json={"text": "pay electricity"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_intents_forwards_and_returns_the_ai_body(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post(
        "/v1/agent/intents",
        json={"text": "  pay my land use charge  ", "locale": "pcm", "channel": "ussd"},
    )
    assert response.status_code == 200
    assert response.json() == INTENT_RESPONSE
    assert agent_client.intent_calls == [
        {"text": "pay my land use charge", "locale": "pcm", "channel": "ussd"}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": "   "},
        {"text": None},
        {"text": "x" * 201},
        {"text": "ok", "locale": "fr"},
        {"text": "ok", "channel": "email"},
    ],
)
def test_intents_rejects_out_of_contract_input_with_400(
    api_client: TestClient,
    session_manager: SessionManager,
    agent_client: FakeAgentClient,
    body: dict,
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/agent/intents", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert agent_client.intent_calls == []


def test_intents_is_rate_limited(
    app: FastAPI, api_client: TestClient, session_manager: SessionManager
) -> None:
    app.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1, default_window_seconds=60
    )
    _sign_in(api_client, session_manager)
    assert api_client.post("/v1/agent/intents", json={"text": "pay"}).status_code == 200
    response = api_client.post("/v1/agent/intents", json={"text": "pay"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in response.headers


def test_intents_maps_an_upstream_client_error(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    agent_client.intent_error = APIError(400, "invalid_request", "Enter what you want to pay.")
    response = api_client.post("/v1/agent/intents", json={"text": "pay"})
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Enter what you want to pay."


def test_intents_reports_an_unreachable_ai_service_as_503(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    agent_client.intent_error = AIUnavailable()
    response = api_client.post("/v1/agent/intents", json={"text": "pay"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == AI_UNAVAILABLE


# --------------------------------------------------------------------------- #
# C-012 surface composition
# --------------------------------------------------------------------------- #
def test_surfaces_requires_a_session(api_client: TestClient) -> None:
    response = api_client.post("/v1/agent/surfaces", json={"task": "confirmation", "context": {}})
    assert response.status_code == 401


def test_surfaces_forwards_task_and_context(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post(
        "/v1/agent/surfaces",
        json={"task": " confirmation ", "context": {"amount": 50000}},
    )
    assert response.status_code == 200
    assert response.json() == SURFACE_RESPONSE
    assert agent_client.surface_calls == [{"task": "confirmation", "context": {"amount": 50000}}]


@pytest.mark.parametrize("task", [None, "", "   "])
def test_surfaces_rejects_a_missing_task_with_400(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient, task
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/agent/surfaces", json={"task": task, "context": {}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert agent_client.surface_calls == []


def test_surfaces_passes_through_the_fallback_shape(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    fallback = {"messages": [], "fallback": "receipt"}
    agent_client.surface_response = fallback
    response = api_client.post("/v1/agent/surfaces", json={"task": "receipt"})
    assert response.status_code == 200
    assert response.json() == fallback


# --------------------------------------------------------------------------- #
# Client transport mapping
# --------------------------------------------------------------------------- #
def _response(status: int, json: Any | None = None, headers: dict | None = None) -> httpx.Response:
    kwargs: dict = {"headers": headers or {}}
    if json is not None:
        kwargs["json"] = json
    return httpx.Response(status, request=httpx.Request("POST", "http://ai/v1"), **kwargs)


def test_upstream_error_forwards_code_and_message() -> None:
    error = _upstream_error(
        _response(400, {"error": {"code": "invalid_request", "message": "Too long."}})
    )
    assert error.status_code == 400
    assert error.code == "invalid_request"
    assert error.message == "Too long."


def test_upstream_rate_limit_carries_retry_after() -> None:
    error = _upstream_error(
        _response(429, {"error": {"code": "rate_limited"}}, {"Retry-After": "7"})
    )
    assert error.status_code == 429
    assert error.code == "rate_limited"
    assert error.headers == {"Retry-After": "7"}


def test_upstream_error_with_an_unexpected_body_is_still_enveloped() -> None:
    error = _upstream_error(_response(400))
    assert error.status_code == 400
    assert error.code == "invalid_request"


def test_http_client_reports_a_transport_failure_as_unavailable() -> None:
    class _Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

    endpoint = AIEndpoint(base_url="http://ai.invalid", timeout_seconds=1.0)
    client = HttpAgentAIClient(endpoint)
    client._client = httpx.Client(  # type: ignore[assignment]
        base_url=endpoint.base_url, transport=_Transport()
    )
    with pytest.raises(APIError) as error:
        client.resolve_intent(text="pay", locale="en", channel="app")
    assert error.value.status_code == 503
    assert error.value.code == AI_UNAVAILABLE


def test_endpoint_prefers_an_explicit_base_url() -> None:
    endpoint = AIEndpoint.from_env({"AI_BASE_URL": "http://ai.internal:9000/"})
    assert endpoint.base_url == "http://ai.internal:9000"


def test_endpoint_builds_from_host_and_port() -> None:
    endpoint = AIEndpoint.from_env({"AI_HOST": "ai", "AI_PORT": "9100"})
    assert endpoint.base_url == "http://ai:9100"


def test_protocol_is_satisfied_by_the_http_client() -> None:
    assert isinstance(HttpAgentAIClient(AIEndpoint("http://ai", 1.0)), AgentAIClient)
