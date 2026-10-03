"""Structured and wire contracts for payment-intent extraction.

The model returns a snake_case object constrained by
:data:`PAYMENT_INTENT_RESPONSE_SCHEMA`; :class:`PaymentIntentExtraction` is the
parsed, validated form. It deliberately has no ``payee`` field on the wire: the payee
is the collecting body of the grounded catalogue record, so the model cannot invent
one (model-quality.md, "Grounding, safety, and refusal behavior"). A response that
does not conform raises :class:`~core.errors.OutputValidationError`, which the service
turns into the documented keyword fallback rather than passing an unverified amount or
payee into a payment.

The response body is camelCase (D-018); the model-internal schema stays snake_case and
is mapped at this boundary. Field shapes align with the C-017 authorise inputs
(``serviceId``, ``amount``, ``currency``, ``payeeReference``) and the payee and amount
carried on the C-026/C-027 case and payment records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from core.errors import OutputValidationError
from core.schemas import DEFAULT_CURRENCY, ServiceSummary


def _mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OutputValidationError(f"{what} must be an object")
    return value


def _optional_str(value: Any, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OutputValidationError(f"{what} must be a string or null")
    text = value.strip()
    return text or None


def _optional_int(value: Any, what: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise OutputValidationError(f"{what} must be an integer or null")
    if value < 0:
        raise OutputValidationError(f"{what} must not be negative")
    return value


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutputValidationError("confidence must be a number")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise OutputValidationError("confidence must be between 0 and 1")
    return result


def _currency(value: Any) -> str:
    if value is None:
        return DEFAULT_CURRENCY
    text = _optional_str(value, "currency")
    if text is None:
        return DEFAULT_CURRENCY
    text = text.upper()
    if len(text) != 3 or not text.isalpha():
        raise OutputValidationError("currency must be a three-letter code")
    return text


@dataclass(frozen=True)
class PaymentIntentExtraction:
    """A grounded amount and payee for one payment request.

    ``service_id`` and ``payee`` are set only when the service resolves to a retrieved
    catalogue record; ``amount`` is integer minor units (kobo for NGN) traceable to the
    user's words or a retrieved record; ``payee_reference`` is only a reference present
    in retrieved data. ``intent_type`` and ``resolved`` are produced by grounding, not
    by the model.
    """

    service_id: str | None = None
    payee: str | None = None
    amount: int | None = None
    currency: str = DEFAULT_CURRENCY
    payee_reference: str | None = None
    confidence: float = 0.0
    language: str = "en"
    clarifying_question: str | None = None
    intent_type: str = "unknown"
    resolved: bool = False

    @classmethod
    def from_mapping(cls, payload: Any) -> PaymentIntentExtraction:
        data = _mapping(payload, "payment intent")
        return cls(
            service_id=_optional_str(data.get("service_id"), "service_id"),
            amount=_optional_int(data.get("amount"), "amount"),
            currency=_currency(data.get("currency")),
            payee_reference=_optional_str(data.get("payee_reference"), "payee_reference"),
            confidence=_confidence(data.get("confidence")),
            language=_optional_str(data.get("language"), "language") or "en",
            clarifying_question=_optional_str(
                data.get("clarifying_question"), "clarifying_question"
            ),
        )


# Passed to the provider so generation is constrained to the contract. ``nullable`` is
# a Gemini schema keyword; :meth:`PaymentIntentExtraction.from_mapping` is the
# authority regardless. There is deliberately no ``payee`` property.
PAYMENT_INTENT_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "service_id": {"type": "string", "nullable": True},
        "amount": {"type": "integer", "nullable": True},
        "currency": {"type": "string"},
        "payee_reference": {"type": "string", "nullable": True},
        "confidence": {"type": "number"},
        "language": {"type": "string"},
        "clarifying_question": {"type": "string", "nullable": True},
    },
    "required": ["confidence", "currency", "language"],
}


# --- Wire models (camelCase, D-018) ----------------------------------------------


class PaymentIntentRequest(BaseModel):
    """The extraction request body.

    ``text`` is bounded and re-checked in the router so the contract's 400 is returned
    rather than the framework default. An explicit unsupported ``locale`` or
    ``channel`` is a 400 in the router.
    """

    model_config = ConfigDict(extra="ignore")

    text: str
    locale: str = "en"
    channel: str = "app"


class PaymentIntentOut(BaseModel):
    """The grounded payment intent the client confirms before authorisation."""

    serviceId: str | None
    payee: str | None
    amount: int | None
    currency: str
    payeeReference: str | None
    intentType: str
    confidence: float
    language: str
    clarifyingQuestion: str | None
    resolved: bool


class ServiceSummaryOut(BaseModel):
    """One candidate service record, matching the C-009/C-010 summary shape."""

    serviceId: str
    name: str
    collectingBody: str
    category: str
    knownAmount: int | None
    currency: str
    status: str
    confidence: float


class PaymentIntentResponse(BaseModel):
    """The extraction response body."""

    paymentIntent: PaymentIntentOut
    candidates: list[ServiceSummaryOut]
    source: str

    @classmethod
    def from_parts(
        cls,
        intent: PaymentIntentExtraction,
        *,
        candidates: Sequence[ServiceSummary],
        source: str,
    ) -> PaymentIntentResponse:
        return cls(
            paymentIntent=PaymentIntentOut(
                serviceId=intent.service_id,
                payee=intent.payee,
                amount=intent.amount,
                currency=intent.currency,
                payeeReference=intent.payee_reference,
                intentType=intent.intent_type,
                confidence=intent.confidence,
                language=intent.language,
                clarifyingQuestion=intent.clarifying_question,
                resolved=intent.resolved,
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
                for item in candidates
            ],
            source=source,
        )


class ErrorBody(BaseModel):
    """The shared error envelope (DELIVERY.md, conventions)."""

    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    """The shared error envelope wrapper."""

    error: ErrorBody
