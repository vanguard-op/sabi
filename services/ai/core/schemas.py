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
from functools import lru_cache
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
    """A resolved payment or discovery intent: only the machine-actionable fields.

    Amounts are integer minor units (kobo for NGN) in ``currency``, never decimal
    major units. ``detected_language`` is the language the model detected or served,
    a machine-actionable signal the client and analytics consume (MQ-001, MQ-004); it
    is null when none was detected. The user-facing message is not part of this
    object: the model authors it as ``reply`` (MQ-001), and the greeting, the
    clarifying question, and the non-resolving replies live there, not in a separate
    field.
    """

    intent_type: str
    confidence: float
    target: str | None = None
    amount: int | None = None
    currency: str = DEFAULT_CURRENCY
    reference: str | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)
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

        return cls(
            intent_type=intent_type,
            confidence=_confidence(data.get("confidence"), "confidence"),
            target=_optional_str(data.get("target"), "target"),
            amount=_optional_int(data.get("amount"), "amount"),
            currency=_currency(data.get("currency")),
            reference=_optional_str(data.get("reference"), "reference"),
            constraints=dict(constraints),
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
            "detected_language": self.detected_language,
        }


@dataclass(frozen=True)
class IntentModelOutput:
    """The model's full JSON output for MQ-001: the reply plus the intent.

    The model authors the user-facing ``reply`` in natural language (the greeting,
    the clarifying question, the refusal, or the non-resolving reply) alongside the
    reduced, machine-actionable intent. ``reply`` is nullable: a missing or empty
    reply is legitimate and the client renders its prewritten fallback string, so a
    blank turn never reaches the user (MQ-001). The reply wording is
    non-deterministic and is never pinned or post-processed; only its safety,
    grounding, and language boundaries are enforced.
    """

    reply: str | None
    intent: Intent

    @classmethod
    def from_mapping(cls, payload: Any) -> IntentModelOutput:
        data = _require_mapping(payload, "intent output")
        return cls(
            reply=_optional_str(data.get("reply"), "reply"),
            intent=Intent.from_mapping(data),
        )


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
# The composition vocabulary the agent composes against is the published Sabi A2UI
# catalog, held as one artifact and validated in :mod:`core.a2ui_catalog` and
# :mod:`core.a2ui`. There is deliberately no component-name list here: a server-side
# hand copy of the client's names drifts from the client and was the defect this
# module must never reintroduce (FEAT-011, MQ-003).

# The task-shaped surfaces the agent composes (C-012, FEAT-011). Every task has a
# client fallback form, so a known task is exactly one that has a fallback. The
# `receipt` task covers both a post-payment receipt and a resolved record the user
# asked about: the task is the same and the resolved record reference rides in the
# request `context`. The prewritten shell (composer, navigation, static chrome) is
# never a task and never composed (FEAT-011).
FALLBACK_TASKS: frozenset[str] = frozenset(
    {"confirmation", "amount_entry", "receipt", "discovery", "verification", "recovery"}
)

# The context fields each task's surface is composed from (C-012, FEAT-011). The
# caller composes the context from real data it holds: a confirmation has a payee
# and an amount, a receipt has the record's own fields, a verification has the
# current status, a recovery has the case state, a discovery has the candidate
# services, and an amount entry knows the currency it is collecting in. Those
# fields are the ones the catalog marks required on the task's component, so the
# caller is responsible for supplying them and the prompt is never asked to invent
# a property the context cannot carry.
#
# A task whose context omits a field here cannot be composed truthfully: the
# serving layer degrades it to the same-task fallback *before* calling the model,
# so the empty-stream escape hatch is reserved for a task the model genuinely
# cannot fit to the catalog, and a missing-context fallback is a logged, explicit
# server decision rather than a silent empty model response. The mapping is also
# rendered into the prompt, so the model and the caller agree on what each task
# requires. `receipt`'s fields mirror the ReceiptCard required set; `discovery`
# carries the candidate rows the ProviderPicker binds to, under the same `services`
# key the client sends and the catalog's ProviderPicker property uses (the existing
# `results` key was an agent-only name no client ever sent, so every real discovery
# request fell back on missing context before reaching the model).
TASK_CONTEXT_FIELDS: Mapping[str, frozenset[str]] = {
    "confirmation": frozenset({"amount", "payee"}),
    "amount_entry": frozenset({"currency"}),
    "receipt": frozenset({"reference", "payee", "amount"}),
    "discovery": frozenset({"services"}),
    "verification": frozenset({"status"}),
    "recovery": frozenset({"status"}),
}


def missing_task_context(task: str, context: Mapping[str, Any] | None) -> tuple[str, ...]:
    """The required context fields a task is missing, in catalog order.

    An empty tuple means the context carries every field the task's surface is
    composed from (``amount_entry`` requires only the collecting currency). An
    unknown task reports nothing here: it is rejected by the router as a 400.
    """

    required = TASK_CONTEXT_FIELDS.get(task)
    if not required:
        return ()
    supplied = context or {}
    # ``None`` is as absent as a missing key: a null carries no value to compose
    # from and the model would have to invent one.
    return tuple(sorted(name for name in required if supplied.get(name) in (None, "", [], {})))


def render_task_context_fields() -> str:
    """The per-task required context, rendered for the composition prompt.

    Keeps the prompt's statement of each task's fields in lockstep with the
    server-side guard: both derive from :data:`TASK_CONTEXT_FIELDS`, so the model
    is never told to require a field the caller is not responsible for, and the
    caller is never required to send a field the prompt does not name.
    """

    lines = []
    for task in sorted(TASK_CONTEXT_FIELDS):
        fields = ", ".join(sorted(TASK_CONTEXT_FIELDS[task]))
        lines.append(f"- {task}: {fields}")
    return "\n".join(lines)


# --- Provider response schemas ---------------------------------------------------
# Passed to the provider so generation is constrained to the contract. ``nullable``
# is a Gemini schema keyword; the parsers above are the authority regardless.

INTENT_RESPONSE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        # The model-authored user-facing message (greeting, clarifying question,
        # refusal, or non-resolving reply), in the request locale. Nullable: the
        # client renders its prewritten fallback when it is absent.
        "reply": {"type": "string", "nullable": True},
        "intent_type": {"type": "string", "enum": sorted(INTENT_TYPES)},
        "target": {"type": "string", "nullable": True},
        "amount": {"type": "integer", "nullable": True},
        "currency": {"type": "string"},
        "reference": {"type": "string", "nullable": True},
        "constraints": {"type": "object"},
        "confidence": {"type": "number"},
        "detected_language": {
            "type": "string",
            "enum": sorted(DETECTED_LANGUAGES),
            "nullable": True,
        },
    },
    "required": ["intent_type", "confidence", "currency", "constraints"],
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

# The composition stream is dynamic and polymorphic: each message body and each
# flat component is a different shape per task and component. The envelope is
# pinned via the provider's ``response_json_schema`` field (draft 2020-12) and the
# model is constrained to a real, populated A2UI stream.
#
# The Developer API cannot carry ``additionalProperties`` at all. The SDK's
# ``_transformers._raise_for_unsupported_mldev_properties`` raises for any truthy
# ``additionalProperties`` (bool or schema object) on the non-Vertex path, so the
# schema must not emit it: a schema carrying the keyword fails at request
# construction with ``ValueError: additionalProperties is only supported in Gemini
# Enterprise Agent Platform mode``, which surfaces as ``ProviderUnavailable``.
# Openness is the JSON Schema default, so the flat component properties stay open
# by simply not closing them: a JSON Schema object without ``additionalProperties``
# permits additional properties, and ``t_schema``/``process_schema`` leaves it
# open. This is the mechanism the Developer API accepts, verified against the SDK's
# own transformer rather than assumed.
#
# The only constructs the SDK's transformer supports are ``type``, ``properties``,
# ``required``, ``items``, ``minItems``, ``enum``, ``nullable`` and ``anyOf``
# (``oneOf``/``allOf``/``not``/``contains``/``prefixItems``/``const`` are rejected
# when the schema is coerced to a ``Schema``). The envelope is therefore stated
# with those:
#
#   * the array requires at least one message (``minItems``);
#   * each message requires a v0.9 ``version`` and a body, via ``anyOf``;
#   * ``createSurface`` requires ``surfaceId``/``catalogId``, ``updateComponents``
#     requires a non-empty ``components`` array, ``updateDataModel`` requires a
#     ``path``;
#   * each component must carry ``id``, a ``component`` name drawn from the
#     published catalog, and the properties that catalog marks ``required``, with
#     their declared primitive types; every other property the catalog declares is
#     described too, so the model is not left to invent an unconstrained one.
#
# The enumerate-only supported keywords mean two A2UI rules the validator cares
# about cannot be stated structurally here: that a message carries *exactly* one
# body (``anyOf`` gives at-least-one) and that the components contain a ``root``
# (no ``contains``/``const`` is available). Those stay with the agent-side
# validator, which is the authority on component names, required properties, the
# single body, and the root (FEAT-011, MQ-003).
#
# The component variants are derived from the same published catalog the
# agent-side pre-send validation uses, so the two cannot disagree on a component's
# required properties (FEAT-011, MQ-003). Optional and task-specific flat
# properties stay open, and the validator remains the authority on names, required
# properties, and executable-content rules.
_PRIMITIVE_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object"})


def _catalog_property_schema(catalog: Any, declared: Any) -> Mapping[str, Any]:
    """A provider-facing schema for one catalog property declaration.

    The catalog declares a property as ``{"type": "integer"}``, a nullable
    ``{"type": ["integer", "null"]}``, an array ``{"type": "array", "items": ...}``,
    or a component ``$ref``. Gemini's ``response_json_schema`` speaks JSON Schema
    2020-12, so a nullable union is expressed as a two-branch ``anyOf`` and a
    component ``$ref`` is inlined from the catalog: the Developer API cannot express
    ``$ref``, so an array of referenced rows (``ProviderPicker.services`` items
    referencing ``ServiceResultRow``) is expanded to the row's own properties and
    ``required`` names. Without that the items schema degenerated to a bare
    ``{"type": "object"}`` that ``{}`` satisfied, so the model emitted empty rows and
    the client rendered blank entries (MQ-003, FEAT-011). Anything the catalog does
    not type is left open rather than guessed.
    """

    if not isinstance(declared, Mapping):
        return {}
    ref = declared.get("$ref")
    if isinstance(ref, str):
        return _catalog_ref_schema(catalog, ref)
    declared_type = declared.get("type")
    if isinstance(declared_type, list):
        branches = [{"type": item} for item in declared_type if item in _PRIMITIVE_TYPES]
        if "null" in declared_type:
            branches.append({"type": "null"})
        if not branches:
            return {}
        return branches[0] if len(branches) == 1 else {"anyOf": branches}
    if declared_type == "array":
        items = declared.get("items")
        if isinstance(items, Mapping):
            return {"type": "array", "items": _catalog_property_schema(catalog, items)}
        return {"type": "array", "items": {}}
    if isinstance(declared_type, str) and declared_type in _PRIMITIVE_TYPES:
        return {"type": declared_type}
    return {}


def _catalog_ref_schema(catalog: Any, ref: str) -> Mapping[str, Any]:
    """A provider-facing object schema for a catalog ``$ref``, inlined.

    The referenced component's declared properties are described and its ``required``
    names are carried over, so a referenced row must be a complete object rather than
    an empty one. A reference that does not point at a catalog component stays a
    permissive object: the agent-side validator is the authority and refuses what it
    cannot resolve.
    """

    prefix = "#/components/"
    name = ref[len(prefix) :] if ref.startswith(prefix) else ""
    if not name or not catalog.defines(name):
        return {"type": "object"}
    properties = {
        prop: _catalog_property_schema(catalog, declared)
        for prop, declared in catalog.property_types(name).items()
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(catalog.required_properties(name)),
    }


def _catalog_component_variant(catalog: Any, name: str) -> Mapping[str, Any]:
    """One ``anyOf`` branch for a catalog component: its flat properties, typed.

    Every property the catalog declares is described (with its declared type), not
    only the required ones. Leaving an optional property unnamed makes it an
    unconstrained entry, and the model then degenerates when it tries to emit one: a
    ``receipt`` context carrying ``kind`` produced a malformed, truncated response
    until ``kind`` was typed. Naming the property keeps the model on the rails; the
    object is left open by not closing it, which is the JSON Schema default and the
    only open-object form the Developer API accepts.
    """

    properties: dict[str, Any] = {
        "id": {"type": "string"},
        "component": {"type": "string", "enum": [name]},
    }
    for prop, declared in catalog.property_types(name).items():
        properties[prop] = _catalog_property_schema(catalog, declared)
    return {
        "type": "object",
        "properties": properties,
        "required": ["id", "component", *catalog.required_properties(name)],
    }


@lru_cache(maxsize=1)
def composition_response_json_schema() -> Mapping[str, Any]:
    """The provider JSON Schema that forces a real, populated A2UI stream.

    Built once from the published Sabi catalog so the provider's constraint and the
    agent-side validator agree on every component's required properties.
    """

    from core.a2ui_catalog import published_catalog

    catalog = published_catalog()
    variants = [_catalog_component_variant(catalog, name) for name in catalog.component_names()]
    # No top-level ``$schema`` marker: the SDK's ``t_schema`` coercion rejects it as
    # an unknown field on ``Schema``, and ``response_json_schema`` is documented as
    # draft 2020-12 by default, so the marker adds nothing the transform or the API
    # needs. The document is still draft 2020-12 JSON Schema.
    return {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "version": {"type": "string", "enum": ["v0.9"]},
                        "createSurface": {
                            "type": "object",
                            "properties": {
                                "surfaceId": {"type": "string"},
                                "catalogId": {"type": "string", "enum": [catalog.catalog_id]},
                            },
                            "required": ["surfaceId", "catalogId"],
                        },
                        "updateComponents": {
                            "type": "object",
                            "properties": {
                                "surfaceId": {"type": "string"},
                                "components": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"anyOf": variants},
                                },
                            },
                            "required": ["surfaceId", "components"],
                        },
                        "updateDataModel": {
                            "type": "object",
                            "properties": {
                                "surfaceId": {"type": "string"},
                                "path": {"type": "string"},
                                "value": {},
                            },
                            "required": ["surfaceId", "path"],
                        },
                    },
                    "required": ["version"],
                    "anyOf": [
                        {"required": ["createSurface"]},
                        {"required": ["updateComponents"]},
                        {"required": ["updateDataModel"]},
                    ],
                },
            },
        },
        "required": ["messages"],
    }
