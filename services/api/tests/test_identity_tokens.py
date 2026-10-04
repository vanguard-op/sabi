"""Unit tests for Google identity tokens on the private-service hops.

The gateway attaches a Google-signed identity token when it calls the private
AI and payment services on Cloud Run, and only then. These tests pin the
presence and audience of the token on both clients, its absence on a local or
test transport, that the token is not logged, and that the Google provider
mints an audience-scoped token through the Cloud Run ID-token path, which needs
no private key and resolves its credential once per audience.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from app.agent.client import AIEndpoint, HttpAgentAIClient
from app.payments.client import ForwardContext, HttpPaymentModuleClient, PaymentEndpoint


class RecordingIdentityProvider:
    """A deterministic stand-in for the Google provider; no network."""

    def __init__(self, value: str = "id-token-xyz") -> None:
        self.value = value
        self.audiences: list[str] = []

    def token(self, audience: str) -> str:
        self.audiences.append(audience)
        return self.value


class CapturingTransport(httpx.BaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._response


def _capture(client: Any, response: httpx.Response) -> CapturingTransport:
    transport = CapturingTransport(response)
    client._client = httpx.Client(base_url=str(client._client.base_url), transport=transport)
    return transport


# --------------------------------------------------------------------------- #
# Agent client -> AI service
# --------------------------------------------------------------------------- #
def test_agent_client_attaches_the_identity_token_and_origin_audience() -> None:
    provider = RecordingIdentityProvider()
    client = HttpAgentAIClient(AIEndpoint("https://ai.internal", 5.0), identity_provider=provider)
    transport = _capture(client, httpx.Response(200, json={"intent": {}, "candidates": []}))

    client.resolve_intent(text="pay rent", locale="en", channel="app")

    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer id-token-xyz"
    assert provider.audiences == ["https://ai.internal"]


def test_agent_client_without_a_provider_stays_unauthenticated() -> None:
    client = HttpAgentAIClient(AIEndpoint("http://localhost:8001", 5.0))
    transport = _capture(client, httpx.Response(200, json={"candidates": []}))

    client.compose_surface(task="confirmation", context={})

    assert "Authorization" not in transport.requests[0].headers


def test_agent_client_never_logs_the_token(caplog: pytest.LogCaptureFixture) -> None:
    client = HttpAgentAIClient(
        AIEndpoint("https://ai.internal", 5.0), identity_provider=RecordingIdentityProvider()
    )
    _capture(client, httpx.Response(500, text="upstream broke"))

    from app.agent.client import AIUnavailable

    with caplog.at_level(logging.DEBUG, logger="sabi.agent"):
        with pytest.raises(AIUnavailable):
            client.resolve_intent(text="x", locale="en", channel="app")

    assert "id-token-xyz" not in caplog.text


# --------------------------------------------------------------------------- #
# Payment client -> payment module
# --------------------------------------------------------------------------- #
def test_payment_client_attaches_the_identity_token_and_origin_audience() -> None:
    provider = RecordingIdentityProvider()
    client = HttpPaymentModuleClient(
        PaymentEndpoint("https://payments.internal", 5.0), identity_provider=provider
    )
    transport = _capture(client, httpx.Response(201, json={"paymentId": "p1"}))

    client.authorise(
        context=ForwardContext(user_id="u1"),
        body={"serviceId": "s1"},
        idempotency_key="k1",
    )

    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer id-token-xyz"
    assert provider.audiences == ["https://payments.internal"]


def test_payment_client_without_a_provider_stays_unauthenticated() -> None:
    client = HttpPaymentModuleClient(PaymentEndpoint("http://localhost:8002", 5.0))
    transport = _capture(client, httpx.Response(200, json={"payments": []}))

    client.list_payments(context=ForwardContext(user_id="u1"), cursor=None, limit=20, status=None)

    assert "Authorization" not in transport.requests[0].headers


def test_payment_client_get_also_attaches_the_token() -> None:
    client = HttpPaymentModuleClient(
        PaymentEndpoint("https://payments.internal", 5.0),
        identity_provider=RecordingIdentityProvider(),
    )
    transport = _capture(client, httpx.Response(200, json={"payments": []}))

    client.list_payments(context=ForwardContext(user_id="u1"), cursor=None, limit=20, status=None)

    assert transport.requests[0].headers["Authorization"] == "Bearer id-token-xyz"


def test_payment_client_never_logs_the_token(caplog: pytest.LogCaptureFixture) -> None:
    client = HttpPaymentModuleClient(
        PaymentEndpoint("https://payments.internal", 5.0),
        identity_provider=RecordingIdentityProvider(),
    )
    _capture(client, httpx.Response(503, text="upstream broke"))

    from app.payments.client import PaymentModuleUnavailable

    with caplog.at_level(logging.DEBUG, logger="sabi.payments"):
        with pytest.raises(PaymentModuleUnavailable):
            client.list_payments(
                context=ForwardContext(user_id="u1"), cursor=None, limit=20, status=None
            )

    assert "id-token-xyz" not in caplog.text


# --------------------------------------------------------------------------- #
# The Google provider itself
# --------------------------------------------------------------------------- #
class FakeIdTokenCredentials:
    """An ID-token credential double: records refreshes, yields a token."""

    def __init__(self, value: str) -> None:
        self._value = value
        self.refresh_requests: list[Any] = []

    def refresh(self, request: Any) -> None:
        self.refresh_requests.append(request)

    @property
    def token(self) -> str:
        return self._value


def test_google_provider_mints_an_audience_scoped_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import identity

    events: dict[str, Any] = {}
    credentials = FakeIdTokenCredentials("id-token-for-ai")

    def _fetch(audience: str, request: Any = None) -> FakeIdTokenCredentials:
        events["audience"] = audience
        events["request"] = request
        return credentials

    from google.oauth2 import id_token as google_id_token

    monkeypatch.setattr(google_id_token, "fetch_id_token_credentials", _fetch)

    provider = identity.GoogleIdentityTokenProvider()
    token = provider.token("https://ai.internal")

    assert token == "id-token-for-ai"
    # The audience reaches the ID-token fetch unchanged: Cloud Run verifies it.
    assert events["audience"] == "https://ai.internal"
    # Resolution goes through the httpx-backed adapter, not google-auth's
    # `requests` transport (which this service does not depend on), and the
    # refresh mints through the same adapter.
    assert events["request"] is provider._request
    assert isinstance(events["request"], identity._HttpxRequest)
    assert credentials.refresh_requests == [provider._request]


def test_google_provider_resolves_credentials_once_per_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import identity

    calls: dict[str, int] = {"fetch": 0}

    def _fetch(audience: str, request: Any = None) -> FakeIdTokenCredentials:
        calls["fetch"] += 1
        return FakeIdTokenCredentials(f"token-{audience}")

    from google.oauth2 import id_token as google_id_token

    monkeypatch.setattr(google_id_token, "fetch_id_token_credentials", _fetch)

    provider = identity.GoogleIdentityTokenProvider()
    assert provider.token("https://ai.internal") == "token-https://ai.internal"
    assert provider.token("https://payments.internal") == "token-https://payments.internal"
    assert provider.token("https://ai.internal") == "token-https://ai.internal"
    # The audience-bound credential is resolved once per audience and reused;
    # repeated calls still mint a token through the same credential.
    assert calls["fetch"] == 2


def test_httpx_transport_implements_the_google_response_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.auth.transport import Response as GoogleResponse

    from app.core import identity

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        content = b"{}"
        headers = {"content-type": "application/json"}

    def _request(method: str, url: str, **kwargs: Any) -> _Response:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _Response()

    import httpx

    monkeypatch.setattr(httpx, "request", _request)
    response = identity._HttpxRequest()(
        "https://metadata.google.internal/computeMetadata/v1/instance/"
        "service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    assert captured["method"] == "GET"
    assert captured["headers"] == {"Metadata-Flavor": "Google"}
    # google-auth validates the transport by duck-typing the interface; the
    # adapter must expose all three attributes.
    assert isinstance(response, GoogleResponse)
    assert response.status == 200
    assert response.headers == {"content-type": "application/json"}
    assert response.data == b"{}"
