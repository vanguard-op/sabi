"""Structured output contracts for the model-backed capabilities.

Each capability has one dataclass and one JSON Schema. The dataclass is the parsed,
validated form the rest of the service uses; the JSON Schema is what the provider is
constrained with. Parsing is deliberately defensive: a response that does not conform
raises :class:`~core.errors.OutputValidationError`, which the serving layer turns into
the documented fallback rather than passing an unverified object to a payment flow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.errors import OutputValidationError

# --- Shared vocabularies ---------------------------------------------------------

INTENT_TYPES: frozenset[str] = frozenset(
    {
        "gov_payment",
        "bill_payment",
        "discovery",
        "status_check",
        "receipt_lookup",
        "non_command",
        "unknown",
    }
)

# Intents that move money. Refusal behavior forbids these when the request is
# unresolved or low-confidence.
PAYMENT_INTENT_TYPES: frozenset[str] = frozenset({"gov_payment", "bill_payment"})

# A greeting or other non-command message. It carries no payment field, asks no
# clarifying question, and is never a coverage miss (MQ-001).
NON_COMMAND_INTENT_TYPE = "non_command"

LANGUAGES: frozenset[str] = frozenset({"en", "pcm"})
DETECTED_LANGUAGES: frozenset[str] = frozenset({"en", "pcm", "ha", "yo", "ig"})

DEFAULT_CURRENCY = "NGN"


def _require_mapping(value: Any, what: str) -> Mapping[str, Any]:
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


def _required_str(value: Any, what: str) -> str:
    text = _optional_str(value, what)
    if text is None:
        raise OutputValidationError(f"{what} is required")
    return text


def _optional_int(value: Any, what: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise OutputValidationError(f"{what} must be an integer or null")
    if value < 0:
        raise OutputValidationError(f"{what} must not be negative")
    return value


def _confidence(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutputValidationError(f"{what} must be a number")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise OutputValidationError(f"{what} must be between 0 and 1")
    return result


def _currency(value: Any) -> str:
    if value is None:
        return DEFAULT_CURRENCY
    text = _required_str(value, "currency").upper()
    if len(text) != 3 or not text.isalpha():
        raise OutputValidationError("currency must be a three-letter code")
    return text


# --- Intent (MQ-001, MQ-004; consumed by C-009) ----------------------------------


@dataclass(frozen=True)
class Intent:
    """A resolved payment or discovery intent.

    Amounts are integer minor units (kobo for NGN) in ``currency``, never decimal
    major units. ``detected_language`` is populated for Nigerian-language
    understanding (MQ-004) and left null for the launch languages.
    """

    intent_type: str
    confidence: float
    target: str | None = None
    amount: int | None = None
    currency: str = DEFAULT_CURRENCY
    reference: str | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)
    language: str = "en"
    clarifying_question: str | None = None
    detected_language: str | None = None

    @classmethod
    def from_mapping(cls, payload: Any) -> Intent:
        data = _require_mapping(payload, "intent")
        intent_type = _required_str(data.get("intent_type"), "intent_type")
        if intent_type not in INTENT_TYPES:
            raise OutputValidationError(f"unknown intent_type: {intent_type}")

        constraints = data.get("constraints") or {}
        if not isinstance(constraints, Mapping):
            raise OutputValidationError("constraints must be an object")

        detected = _optional_str(data.get("detected_language"), "detected_language")
        if detected is not None and detected not in DETECTED_LANGUAGES:
            raise OutputValidationError(f"unknown detected_language: {detected}")

        language = _optional_str(data.get("language"), "language") or "en"

        return cls(
            intent_type=intent_type,
            confidence=_confidence(data.get("confidence"), "confidence"),
            target=_optional_str(data.get("target"), "target"),
            amount=_optional_int(data.get("amount"), "amount"),
            currency=_currency(data.get("currency")),
            reference=_optional_str(data.get("reference"), "reference"),
            constraints=dict(constraints),
            language=language,
            clarifying_question=_optional_str(
                data.get("clarifying_question"), "clarifying_question"
            ),
            detected_language=detected,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "target": self.target,
            "amount": self.amount,
            "currency": self.currency,
            "reference": self.reference,
            "constraints": dict(self.constraints),
            "confidence": self.confidence,
            "language": self.language,
            "clarifying_question": self.clarifying_question,
            "detected_language": self.detected_language,
        }


# --- Service summary (MQ-002; consumed by C-009 and C-010) -----------------------


@dataclass(frozen=True)
class ServiceSummary:
    """A catalogue result as the client and the contract consume it."""

    service_id: str
    name: str
    collecting_body: str
    category: str
    confidence: float
    known_amount: int | None = None
    currency: str = DEFAULT_CURRENCY
    status: str = "active"

    @classmethod
    def from_mapping(cls, payload: Any) -> ServiceSummary:
        data = _require_mapping(payload, "service")
        return cls(
            service_id=_required_str(data.get("service_id"), "service_id"),
            name=_required_str(data.get("name"), "name"),
            collecting_body=_required_str(data.get("collecting_body"), "collecting_body"),
            category=_required_str(data.get("category"), "category"),
            confidence=_confidence(data.get("confidence"), "confidence"),
            known_amount=_optional_int(data.get("known_amount"), "known_amount"),
            currency=_currency(data.get("currency")),
            status=_optional_str(data.get("status"), "status") or "active",
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "collecting_body": self.collecting_body,
            "category": self.category,
            "known_amount": self.known_amount,
            "currency": self.currency,
            "status": self.status,
            "confidence": self.confidence,
        }


# --- Ranking (MQ-002) ------------------------------------------------------------


@dataclass(frozen=True)
class RankingResult:
    """A model ranking over a retrieved candidate set."""

    results: tuple[ServiceSummary, ...]
    no_match: bool = False

    @classmethod
    def from_mapping(cls, payload: Any) -> RankingResult:
        data = _require_mapping(payload, "ranking")
        raw = data.get("results") or []
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise OutputValidationError("results must be an array")
        if len(raw) > 5:
            raise OutputValidationError("results must contain at most five entries")
        results = tuple(ServiceSummary.from_mapping(item) for item in raw)
        no_match = bool(data.get("no_match", not results))
        if not results and not no_match:
            raise OutputValidationError("empty results require no_match=true")
        return cls(results=results, no_match=no_match)


# --- Composition (MQ-003) --------------------------------------------------------

COMPOSITION_MESSAGE_TYPES: frozenset[str] = frozenset(
    {"createSurface", "updateComponents", "updateDataModel"}
)

# The composable components named in the shared component catalogue
# (screens.md, "Shared / Common Components"). The client catalogue is authoritative;
# the composition feature passes the exact set it validates against.
CLIENT_COMPONENT_CATALOGUE: frozenset[str] = frozenset(
    {
        "NavigationShell",
        "ComposedTaskSurface",
        "ConfirmationSummary",
        "ServiceResultRow",
        "StatusPill",
        "ReceiptCard",
        "EmptyState",
        "ErrorState",
        "OfflineBanner",
        "SuccessToast",
        "AmountEntry",
        "ProviderPicker",
    }
)

FALLBACK_TASKS: frozenset[str] = frozenset({"confirmation", "amount_entry", "receipt", "discovery"})


# --- Provider response schemas ---------------------------------------------------
# Passed to the provider so generation is constrained to the contract. ``nullable``
# is a Gemini schema keyword; the parsers above are the authority regardless.

INTENT_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "intent_type": {"type": "string", "enum": sorted(INTENT_TYPES)},
        "target": {"type": "string", "nullable": True},
        "amount": {"type": "integer", "nullable": True},
        "currency": {"type": "string"},
        "reference": {"type": "string", "nullable": True},
        "constraints": {"type": "object"},
        "confidence": {"type": "number"},
        "language": {"type": "string"},
        "clarifying_question": {"type": "string", "nullable": True},
        "detected_language": {
            "type": "string",
            "enum": sorted(DETECTED_LANGUAGES),
            "nullable": True,
        },
    },
    "required": ["intent_type", "confidence", "currency", "language", "constraints"],
}

SERVICE_SUMMARY_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "service_id": {"type": "string"},
        "name": {"type": "string"},
        "collecting_body": {"type": "string"},
        "category": {"type": "string"},
        "known_amount": {"type": "integer", "nullable": True},
        "currency": {"type": "string"},
        "status": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["service_id", "name", "collecting_body", "category", "confidence"],
}

RANKING_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "results": {"type": "array", "items": SERVICE_SUMMARY_SCHEMA, "maxItems": 5},
        "no_match": {"type": "boolean"},
    },
    "required": ["results", "no_match"],
}

COMPOSITION_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "messages": {
            "type": "array",
            "items": {"type": "object"},
        },
    },
    "required": ["messages"],
}
