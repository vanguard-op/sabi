"""Unit tests for the gateway agent module (C-009, C-012).

They exercise what the gateway owns: the authenticated account-owner gate, rate
limiting, the contract's request bounds, the pass-through of the AI service body,
the catalogue candidates it forwards for grounding, and the mapping of an upstream
4xx and an unreachable service. The model-backed behaviour itself is covered by
the AI service's own tests, not here.
"""

from __future__ import annotations

import json
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
from app.db.models import Service

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

HISTORY = [
    {"role": "user", "text": "I wan pay my light bill"},
    {"role": "assistant", "text": "Which electricity biller?"},
]


class FakeAgentClient:
    """A deterministic stand-in for the AI service client."""

    def __init__(self) -> None:
        self.intent_calls: list[dict[str, Any]] = []
        self.surface_calls: list[dict[str, Any]] = []
        self.intent_error: APIError | None = None
        self.surface_error: APIError | None = None
        self.intent_response: dict[str, Any] = INTENT_RESPONSE
        self.surface_response: dict[str, Any] = SURFACE_RESPONSE

    def resolve_intent(
        self,
        *,
        text: str,
        locale: str,
        channel: str,
        history: list[dict[str, Any]] | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        call: dict[str, Any] = {"text": text, "locale": locale, "channel": channel}
        if history is not None:
            call["history"] = history
        if candidates:
            call["candidates"] = candidates
        self.intent_calls.append(call)
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


@pytest.fixture
def seed_service(db_session_factory: sessionmaker):
    """Insert a catalogue service into the isolated store the gateway reads."""

    def add(**overrides: object) -> Service:
        values: dict[str, object] = {
            "type": "government",
            "name": "Ikeja Local Government Council",
            "collecting_body": "Ikeja LGA",
            "category": "levy",
            "aliases": ["Ikeja Council"],
            "currency": "NGN",
            "status": "active",
        }
        values.update(overrides)
        with db_session_factory() as db:
            service = Service(**values)
            db.add(service)
            db.commit()
            db.refresh(service)
            return service

    return add


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


def test_intents_is_valid_without_history(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/agent/intents", json={"text": "pay electricity"})
    assert response.status_code == 200
    # An absent history stays absent on the forwarded call.
    assert agent_client.intent_calls == [
        {"text": "pay electricity", "locale": "en", "channel": "app"}
    ]


def test_intents_forwards_history_intact(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post(
        "/v1/agent/intents",
        json={"text": "the one I mentioned", "history": HISTORY},
    )
    assert response.status_code == 200
    assert agent_client.intent_calls == [
        {
            "text": "the one I mentioned",
            "locale": "en",
            "channel": "app",
            "history": HISTORY,
        }
    ]


def test_intents_forwards_catalogue_candidates(
    api_client: TestClient,
    session_manager: SessionManager,
    agent_client: FakeAgentClient,
    seed_service,
) -> None:
    _sign_in(api_client, session_manager)
    service = seed_service()
    seed_service(
        name="Airtime Topup",
        collecting_body="Telco",
        category="airtime",
        aliases=["Airtime"],
    )

    response = api_client.post("/v1/agent/intents", json={"text": "Ikeja levy"})

    assert response.status_code == 200
    calls = agent_client.intent_calls
    assert len(calls) == 1
    candidates = calls[0]["candidates"]
    # Only the ranking match for the request text is forwarded, and it carries the
    # ServiceSummary fields the AI service grounds on.
    assert candidates == [
        {
            "serviceId": service.id,
            "name": "Ikeja Local Government Council",
            "collectingBody": "Ikeja LGA",
            "category": "levy",
            "knownAmount": None,
            "currency": "NGN",
            "status": "active",
        }
    ]


def test_intents_candidate_set_is_bounded(
    api_client: TestClient,
    session_manager: SessionManager,
    agent_client: FakeAgentClient,
    seed_service,
) -> None:
    _sign_in(api_client, session_manager)
    for index in range(25):
        seed_service(name=f"Levy Office {index:02d}", collecting_body="Levy")

    response = api_client.post("/v1/agent/intents", json={"text": "levy"})

    assert response.status_code == 200
    assert len(agent_client.intent_calls[0]["candidates"]) == 20


def test_intents_forwards_no_candidates_when_the_catalogue_is_empty(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/agent/intents", json={"text": "Ikeja levy"})
    assert response.status_code == 200
    # An empty catalogue forwards no candidates rather than an empty array.
    assert agent_client.intent_calls == [{"text": "Ikeja levy", "locale": "en", "channel": "app"}]


def test_intents_response_is_unchanged_when_candidates_are_forwarded(
    api_client: TestClient,
    session_manager: SessionManager,
    agent_client: FakeAgentClient,
    seed_service,
) -> None:
    _sign_in(api_client, session_manager)
    seed_service()
    response = api_client.post("/v1/agent/intents", json={"text": "Ikeja levy"})
    # The forwarded grounding set is internal; the C-009 response is the AI body.
    assert response.status_code == 200
    assert response.json() == INTENT_RESPONSE


@pytest.mark.parametrize(
    "history",
    [
        "not a list",
        {"role": "user", "text": "hi"},
        [{"role": "user"}],
        [{"role": "user", "text": 5}],
        [{"role": "user", "text": "hi"}, "hello"],
    ],
)
def test_intents_rejects_a_malformed_history_with_400(
    api_client: TestClient,
    session_manager: SessionManager,
    agent_client: FakeAgentClient,
    history: object,
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post("/v1/agent/intents", json={"text": "pay", "history": history})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert agent_client.intent_calls == []


def test_intents_rejects_an_unknown_history_role_with_400(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    response = api_client.post(
        "/v1/agent/intents",
        json={"text": "pay", "history": [{"role": "system", "text": "hi"}]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert agent_client.intent_calls == []


def test_intents_rejects_more_than_six_history_entries_with_400(
    api_client: TestClient, session_manager: SessionManager, agent_client: FakeAgentClient
) -> None:
    _sign_in(api_client, session_manager)
    history = [{"role": "user", "text": f"turn {index}"} for index in range(7)]
    response = api_client.post("/v1/agent/intents", json={"text": "pay", "history": history})
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


class _CapturingTransport(httpx.BaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._response


def _capturing_client() -> tuple[HttpAgentAIClient, _CapturingTransport]:
    client = HttpAgentAIClient(AIEndpoint("http://ai", 1.0))
    transport = _CapturingTransport(_response(200, INTENT_RESPONSE))
    client._client = httpx.Client(base_url="http://ai", transport=transport)
    return client, transport


def test_http_client_forwards_history_in_the_c009_body() -> None:
    client, transport = _capturing_client()

    client.resolve_intent(text="pay", locale="en", channel="app", history=HISTORY)

    body = json.loads(transport.requests[0].content)
    assert body == {"text": "pay", "locale": "en", "channel": "app", "history": HISTORY}


def test_http_client_omits_an_absent_history_from_the_c009_body() -> None:
    client, transport = _capturing_client()

    client.resolve_intent(text="pay", locale="en", channel="app")

    body = json.loads(transport.requests[0].content)
    assert body == {"text": "pay", "locale": "en", "channel": "app"}


def test_http_client_forwards_candidates_in_the_c009_body() -> None:
    client, transport = _capturing_client()
    candidates = [{"serviceId": "svc-1", "name": "Ikeja LGA", "currency": "NGN"}]

    client.resolve_intent(text="pay", locale="en", channel="app", candidates=candidates)

    body = json.loads(transport.requests[0].content)
    assert body["candidates"] == candidates


def test_http_client_omits_empty_candidates_from_the_c009_body() -> None:
    client, transport = _capturing_client()

    client.resolve_intent(text="pay", locale="en", channel="app", candidates=[])

    # An empty set stays off the wire so the AI service uses its own index.
    body = json.loads(transport.requests[0].content)
    assert "candidates" not in body


def test_endpoint_prefers_an_explicit_base_url() -> None:
    endpoint = AIEndpoint.from_env({"AI_BASE_URL": "http://ai.internal:9000/"})
    assert endpoint.base_url == "http://ai.internal:9000"


def test_endpoint_builds_from_host_and_port() -> None:
    endpoint = AIEndpoint.from_env({"AI_HOST": "ai", "AI_PORT": "9100"})
    assert endpoint.base_url == "http://ai:9100"


def test_protocol_is_satisfied_by_the_http_client() -> None:
    assert isinstance(HttpAgentAIClient(AIEndpoint("http://ai", 1.0)), AgentAIClient)
