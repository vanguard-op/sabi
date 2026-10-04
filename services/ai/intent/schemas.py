"""Wire models for intent resolution (C-009).

Wire fields are camelCase (D-018); the model's internal schema stays snake_case and
is mapped here at the boundary. The field set and nullability match C-009 exactly, so
the client can render the intent without reshaping it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.history import MAX_HISTORY_TURNS
from core.retrieval import RetrievedRecord
from core.serving import IntentResolution

# At most this many forwarded candidates are accepted into grounding. It matches the
# retrieval breadth (RETRIEVAL_LIMIT), so a forwarded set cannot grow the prompt wider
# than the index it replaces.
MAX_CANDIDATES = 20


class HistoryTurn(BaseModel):
    """One prior turn of the exchange (C-009 ``history``), oldest first.

    A malformed entry, an unknown role, or more than six turns fails schema
    validation, which the app maps to the contract's 400 with the shared envelope.
    """

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"]
    text: str


class CandidateService(BaseModel):
    """One candidate service record forwarded by the gateway.

    The API gateway owns the catalogue, so on this private hop it forwards the
    candidate services it already holds and the AI service grounds on them instead of
    its own uninstalled index. The wire shape is the C-009 ``ServiceSummary`` the
    gateway speaks in camelCase (D-018); the snake_case spellings the AI service uses
    internally are also accepted so the record survives either serialisation. Fields
    beyond the identifier are optional here because a partial record can still ground a
    target; a candidate without a ``serviceId`` cannot be cited, so it is rejected as a
    malformed record (the shared 400) rather than grounded on.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    service_id: str = Field(
        validation_alias=AliasChoices("serviceId", "service_id", "id"),
        serialization_alias="serviceId",
    )
    name: str | None = None
    collecting_body: str | None = Field(
        default=None,
        validation_alias=AliasChoices("collectingBody", "collecting_body"),
    )
    category: str | None = None
    known_amount: int | None = Field(
        default=None,
        validation_alias=AliasChoices("knownAmount", "known_amount"),
    )
    currency: str = "NGN"
    status: str = "active"
    confidence: float = 0.0

    def to_record(self) -> RetrievedRecord:
        """Map the candidate to the grounding record shape the serving layer uses.

        Only fields present on the forwarded record are carried; absent fields stay
        absent so a missing amount can never be read as zero. ``confidence`` grounds
        no fact and is intentionally dropped.
        """

        fields: dict[str, Any] = {"service_id": self.service_id, "currency": self.currency}
        if self.name is not None:
            fields["name"] = self.name
        if self.collecting_body is not None:
            fields["collecting_body"] = self.collecting_body
        if self.category is not None:
            fields["category"] = self.category
        if self.known_amount is not None:
            fields["known_amount"] = self.known_amount
        if self.status:
            fields["status"] = self.status
        return RetrievedRecord(record_id=self.service_id, kind="service", fields=fields)


def candidates_to_records(
    candidates: Sequence[CandidateService] | None,
) -> tuple[RetrievedRecord, ...]:
    """Convert forwarded candidates to grounding records, preserving order."""

    if not candidates:
        return ()
    return tuple(candidate.to_record() for candidate in candidates)


class IntentRequest(BaseModel):
    """The C-009 request body plus the gateway's grounding candidates.

    ``text`` is bounded at 200 characters here and re-checked in the router so the
    contract's 400 is returned rather than the framework default. ``locale`` and
    ``channel`` default, and an explicit unsupported value is a 400 in the router.
    ``history`` is optional, oldest first, and at most six turns.

    ``candidates`` is the optional grounding set the gateway forwards on this private
    hop; it is the authoritative retrieval set when present and is not part of the
    client-facing C-009 request. It is capped at the retrieval breadth so a caller
    cannot inflate the prompt, and an over-sized array is a 400 in the router.
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
    candidates: list[CandidateService] | None = Field(
        default=None,
        max_length=MAX_CANDIDATES,
        description="grounding services forwarded by the gateway, when present",
    )


class IntentOut(BaseModel):
    """The reduced, machine-actionable intent (C-009 ``intent``).

    The model authors its user-facing message as the response's top-level ``reply``;
    the greeting, the clarifying question, and the refusal are part of that reply, so
    the intent carries only the fields the client acts on. ``detectedLanguage`` is the
    language the model detected or served, a machine-actionable signal the client and
    analytics consume (MQ-001, MQ-004); it is null when none was detected.
    """

    intentType: str
    target: str | None
    amount: int | None
    currency: str
    reference: str | None
    constraints: dict[str, Any]
    confidence: float
    detectedLanguage: str | None


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
    """The C-009 response body.

    ``reply`` is the model-authored message in ``locale``; it is null when none was
    produced, was empty, or broke a reply boundary, and the client renders its
    prewritten fallback string.
    """

    reply: str | None
    intent: IntentOut
    candidates: list[ServiceSummaryOut]
    source: str

    @classmethod
    def from_resolution(cls, result: IntentResolution) -> IntentResponse:
        intent = result.intent
        return cls(
            reply=result.reply,
            intent=IntentOut(
                intentType=intent.intent_type,
                target=intent.target,
                amount=intent.amount,
                currency=intent.currency,
                reference=intent.reference,
                constraints=dict(intent.constraints),
                confidence=intent.confidence,
                detectedLanguage=intent.detected_language,
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
