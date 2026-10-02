"""Boundary from the API gateway to the AI service.

The gateway forwards the two agent capabilities the client needs to the private
model-serving service (architecture.md, "API Gateway / Backend-for-Frontend";
"Agent Orchestrator"). The AI service performs no authentication of its own
because it sits behind this hop, so the gateway owns session checks, rate
limiting, and input validation before the call.

The upstream service returns the same shared error envelope the API uses, so an
upstream 400 or 429 is re-raised with its code and message intact. A transport
failure, a timeout, or an unexpected status means the capability cannot be
reached at all; that is reported as ``ai_unavailable`` (503) rather than being
dressed up as a model fallback, because the gateway has no grounded answer to
give the client. The in-service model fallback (``source: fallback``) is the AI
service's job and passes through unchanged.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.errors import APIError, ErrorCode

logger = logging.getLogger("sabi.agent")

# Transport error code for an unreachable AI service. It is a gateway condition,
# not part of the C-009/C-012 error lists, which describe direct calls.
AI_UNAVAILABLE = "ai_unavailable"

_DEFAULT_AI_HOST = "localhost"
_DEFAULT_AI_PORT = 8001
_DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, slots=True)
class AIEndpoint:
    """Resolved base URL and timeout for the AI service."""

    base_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AIEndpoint:
        source = os.environ if env is None else env
        base = source.get("AI_BASE_URL", "").strip()
        if base:
            return cls(base_url=base.rstrip("/"), timeout_seconds=_timeout(source))
        host = source.get("AI_HOST", "").strip() or _DEFAULT_AI_HOST
        port = source.get("AI_PORT", "").strip() or str(_DEFAULT_AI_PORT)
        return cls(base_url=f"http://{host}:{port}", timeout_seconds=_timeout(source))


def _timeout(source: dict[str, str]) -> float:
    raw = source.get("AI_REQUEST_TIMEOUT_SECONDS", "").strip()
    try:
        return float(raw) if raw else _DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


@runtime_checkable
class AgentAIClient(Protocol):
    """The two model-backed capabilities the gateway forwards."""

    def resolve_intent(self, *, text: str, locale: str, channel: str) -> dict[str, Any]: ...

    def compose_surface(self, *, task: str, context: dict[str, Any]) -> dict[str, Any]: ...


class HttpAgentAIClient:
    """Forwards to the AI service over HTTP with a single pooled client."""

    def __init__(self, endpoint: AIEndpoint) -> None:
        self._client = httpx.Client(
            base_url=endpoint.base_url,
            timeout=endpoint.timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def resolve_intent(self, *, text: str, locale: str, channel: str) -> dict[str, Any]:
        return self._post(
            "/v1/agent/intents",
            json={"text": text, "locale": locale, "channel": channel},
        )

    def compose_surface(self, *, task: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/agent/surfaces", json={"task": task, "context": context})

    def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=json)
        except httpx.HTTPError:
            # Never surface the underlying transport detail; it can carry the
            # service address. The client gets one retryable message.
            logger.warning("AI service call failed", extra={"path": path})
            raise AIUnavailable() from None

        if response.status_code >= 500:
            logger.warning(
                "AI service returned a server error",
                extra={"path": path, "status": response.status_code},
            )
            raise AIUnavailable()
        if response.status_code >= 400:
            raise _upstream_error(response)
        try:
            payload = response.json()
        except ValueError:
            logger.warning("AI service returned a non-JSON body", extra={"path": path})
            raise AIUnavailable() from None
        if not isinstance(payload, dict):
            raise AIUnavailable()
        return payload


class AIUnavailable(APIError):
    """The AI service could not be reached or answered unexpectedly."""

    def __init__(self) -> None:
        super().__init__(
            503,
            AI_UNAVAILABLE,
            "The assistant is unavailable right now. Try again shortly.",
        )


def _upstream_error(response: httpx.Response) -> APIError:
    """Translate a 4xx from the AI service into the same contract error.

    The AI service already returns the shared envelope, so its code and message
    are forwarded; an unexpected body falls back to the code implied by the
    status. Only the fields the envelope defines are read, never the upstream URL
    or headers.
    """

    status = response.status_code
    if status == 429:
        retry_after = response.headers.get("Retry-After")
        headers = {"Retry-After": retry_after} if retry_after else None
        return APIError(
            429,
            ErrorCode.RATE_LIMITED,
            "Too many requests. Try again shortly.",
            headers=headers,
        )

    code = ErrorCode.INVALID_REQUEST
    message = "That request is not valid."
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            if isinstance(error.get("code"), str) and error["code"]:
                code = error["code"]
            if isinstance(error.get("message"), str) and error["message"]:
                message = error["message"]
    return APIError(status, code, message)


def build_agent_client(endpoint: AIEndpoint | None = None) -> HttpAgentAIClient:
    return HttpAgentAIClient(endpoint or AIEndpoint.from_env())
