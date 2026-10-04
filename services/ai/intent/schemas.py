"""Wire models for intent resolution (C-009).

Wire fields are camelCase (D-018); the model's internal schema stays snake_case and
is mapped here at the boundary. The field set and nullability match C-009 exactly, so
the client can render the intent without reshaping it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.history import MAX_HISTORY_TURNS
from core.serving import IntentResolution


class HistoryTurn(BaseModel):
    """One prior turn of the exchange (C-009 ``history``), oldest first.

    A malformed entry, an unknown role, or more than six turns fails schema
    validation, which the app maps to the contract's 400 with the shared envelope.
    """

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"]
    text: str


class IntentRequest(BaseModel):
    """The C-009 request body.

    ``text`` is bounded at 200 characters here and re-checked in the router so the
    contract's 400 is returned rather than the framework default. ``locale`` and
    ``channel`` default, and an explicit unsupported value is a 400 in the router.
    ``history`` is optional, oldest first, and at most six turns.
    """

    model_config = ConfigDict(extra="ignore")

    text: str = Field(description="free-form user request, at most 200 characters")
    locale: str = "en"
    channel: str = "app"
    history: list[HistoryTurn] | None = Field(
        default=None,
        max_length=MAX_HISTORY_TURNS,
        description="earlier turns of the conversation, oldest first, at most six",
    )


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
    """The C-009 response body."""

    intent: IntentOut
    candidates: list[ServiceSummaryOut]
    source: str

    @classmethod
    def from_resolution(cls, result: IntentResolution) -> IntentResponse:
        intent = result.intent
        return cls(
            intent=IntentOut(
                intentType=intent.intent_type,
                target=intent.target,
                amount=intent.amount,
                currency=intent.currency,
                reference=intent.reference,
                constraints=dict(intent.constraints),
                confidence=intent.confidence,
                language=intent.language,
                clarifyingQuestion=intent.clarifying_question,
            ),
            candidates=[
                ServiceSummaryOut(
                    serviceId=item.service_id,
                    name=item.name,
                    collectingBody=item.collecting_body,
                    category=item.category,
                    knownAmount=item.known_amount,
                    currency=item.currency,
                    status=item.status,
                    confidence=item.confidence,
                )
                for item in result.candidates
            ],
            source=result.source,
        )


class ErrorBody(BaseModel):
    """The shared error envelope (DELIVERY.md, conventions)."""

    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody = Field(description="error envelope")
