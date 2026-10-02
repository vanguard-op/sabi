"""Wire models for the gateway agent endpoints (C-009, C-012).

The gateway forwards the AI service's JSON body unchanged, so these models are the
contract boundary: they validate the inbound request and give the OpenAPI document
the frozen response shape. Field names are camelCase on the wire (D-018); the
upstream AI service speaks the same shape, so no reshaping happens here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class IntentRequest(BaseModel):
    """The C-009 request body.

    ``text`` is optional at the schema layer so the router can return the
    contract's 400 for a missing or empty value rather than the framework's 422;
    defaults match the AI service.
    """

    model_config = ConfigDict(extra="ignore")

    text: str | None = None
    locale: str = "en"
    channel: str = "app"


class IntentOut(BaseModel):
    """The resolved structured intent (C-009 ``intent``)."""

    intentType: str
    target: str | None
    amount: int | None
    currency: str
    reference: str | None
    constraints: dict[str, Any]
    confidence: float
    language: str
    clarifyingQuestion: str | None


class ServiceSummaryOut(BaseModel):
    """One candidate service record (C-009 ``candidates``)."""

    serviceId: str
    name: str
    collectingBody: str
    category: str
    knownAmount: int | None
    currency: str
    status: str
    confidence: float


class IntentResponse(BaseModel):
    """The C-009 response body, exactly as the AI service returns it."""

    intent: IntentOut
    candidates: list[ServiceSummaryOut]
    source: str


class SurfaceRequest(BaseModel):
    """The C-012 request body.

    ``task`` is optional at the schema layer so the router can return the
    contract's 400 for an unknown task rather than the framework's 422; context
    is untrusted, free-form task context.
    """

    model_config = ConfigDict(extra="ignore")

    task: str | None = None
    context: dict[str, Any] = {}


class SurfaceResponse(BaseModel):
    """The C-012 response body: declarative UI messages and the fallback key."""

    messages: list[dict[str, Any]]
    fallback: str
