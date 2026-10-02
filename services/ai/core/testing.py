"""Deterministic test doubles for the model-serving foundation.

Downstream tests inject these so the model is mocked or recorded and the suite stays
deterministic. Nothing here touches the network or the google-genai SDK.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from core.errors import ProviderUnavailable
from core.provider import ModelProvider, ModelRequest, ModelResponse, ModelUsage
from core.retrieval import KeywordRetrievalIndex, RetrievedRecord


class FakeModelProvider(ModelProvider):
    """A provider that replays configured responses and records every request.

    ``responder`` takes precedence and receives the request; otherwise responses are
    consumed in order. A response that is an exception instance is raised, so provider
    failure paths are exercised without touching the network.
    """

    def __init__(
        self,
        responses: Iterable[ModelResponse | BaseException] | None = None,
        *,
        responder: Callable[[ModelRequest], ModelResponse] | None = None,
    ) -> None:
        self.requests: list[ModelRequest] = []
        self._responses: deque[ModelResponse | BaseException] = deque(responses or [])
        self._responder = responder

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._responder is not None:
            return self._responder(request)
        if not self._responses:
            raise ProviderUnavailable("no fake response configured")
        response = self._responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return response

    @property
    def last_request(self) -> ModelRequest:
        return self.requests[-1]


def json_response(
    payload: Mapping[str, Any] | list[Any],
    *,
    model_id: str = "gemini-3-flash-preview",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> ModelResponse:
    """Build a provider response whose text is the given JSON payload."""

    text = json.dumps(payload)
    return ModelResponse(
        text=text,
        parsed=payload,
        model_id=model_id,
        usage=ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        latency_ms=1,
        finish_reason="STOP",
    )


def text_response(text: str, *, model_id: str = "gemini-3-flash-preview") -> ModelResponse:
    """Build a provider response with unparseable text."""

    return ModelResponse(
        text=text,
        parsed=None,
        model_id=model_id,
        usage=ModelUsage(input_tokens=10, output_tokens=5),
        latency_ms=1,
    )


@dataclass(frozen=True)
class FakeCandidate:
    """Convenience description for seeding a retrieval index."""

    service_id: str
    name: str
    collecting_body: str
    category: str
    known_amount: int | None = None
    currency: str = "NGN"
    status: str = "active"
    aliases: tuple[str, ...] = ()

    def to_record(self) -> RetrievedRecord:
        fields: dict[str, Any] = {
            "service_id": self.service_id,
            "name": self.name,
            "collecting_body": self.collecting_body,
            "category": self.category,
            "currency": self.currency,
            "status": self.status,
            "known_amount": self.known_amount,
        }
        if self.aliases:
            fields["aliases"] = list(self.aliases)
        return RetrievedRecord.from_service(fields)


def index_over(candidates: Iterable[FakeCandidate]) -> KeywordRetrievalIndex:
    """Build a deterministic retrieval index from candidate descriptions."""

    return KeywordRetrievalIndex([candidate.to_record() for candidate in candidates])
