"""Guardrails the quality contract requires before output reaches a user.

These are product decisions enforced in code, not left to the implementer:

* Refusal: below the confidence threshold the assistant asks one clarifying question,
  building on the earlier turns, up to three in one conversation, and never presents a
  payment intent; at the bound it declines instead of asking again (MQ-001).
* Non-command: a greeting or small talk is classified ``non_command``, which carries
  no payment field, asks no clarifying question, and is never a coverage miss (MQ-001).
* No invention: grounding drops an identifier, amount, or reference the model could
  not trace (see :mod:`core.grounding`).
* Language: a detected language that is not enabled falls back to English with a note
  rather than mis-resolving (MQ-004).
* Composition: only client-catalogue components, and never executable code, scripts,
  or external resource loads (MQ-003).

Nothing here raises for a merely imperfect model answer; it either repairs the
sequence or marks it unresolved so the caller can ask, decline, or render a fallback.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from core.config import INTENT_CONFIDENCE_CUTOFF
from core.grounding import GroundingContext, ground_intent
from core.history import CLARIFICATION_LIMIT, CLARIFICATION_LIMIT_KEY
from core.schemas import (
    COMPOSITION_MESSAGE_TYPES,
    NON_COMMAND_INTENT_TYPE,
    PAYMENT_INTENT_TYPES,
    Intent,
)

# A resolved request must clear this confidence before a payment intent is presented.
# The cutoff is a single product decision fixed at 0.70 (D-017) and stated in
# model-quality.md, "MQ-001" and "Quality bar"; below it the assistant asks one
# clarifying question, up to the three-question conversation bound. It is evaluated,
# never tuned per run.
INTENT_CONFIDENCE_THRESHOLD = INTENT_CONFIDENCE_CUTOFF

# A ranking result below this relevance is not shown as a match.
RANKING_CONFIDENCE_THRESHOLD = 0.50

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "pcm"})

DEFAULT_CLARIFYING_QUESTION = "Which service or biller do you want to pay?"
LANGUAGE_FALLBACK_NOTE = "I'll continue in English for this request."

_EXECUTABLE_PATTERNS = (
    "<script",
    "</script",
    "javascript:",
    "data:text/html",
    "<iframe",
    "<object",
    "<embed",
    "eval(",
    "function(",
    "onclick=",
    "onload=",
)
_EXTERNAL_LOAD_RE = re.compile(r"(?:https?://|//)[^\s\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class GuardrailOutcome:
    """The intent after guardrails, with the flags that explain any repair."""

    intent: Intent
    flags: frozenset[str] = frozenset()
    citations: tuple[str, ...] = ()
    language_fallback: bool = False
    note: str | None = None


def normalize_question(question: str | None) -> str:
    """Return exactly one question.

    A model may return a paragraph or several questions; the contract allows exactly
    one. Everything after the first question mark is dropped, and a statement with no
    question mark is given one.
    """

    if not question or not question.strip():
        return DEFAULT_CLARIFYING_QUESTION
    text = question.strip()
    end = text.find("?")
    if end == -1:
        return text.rstrip(".! ") + "?"
    return text[: end + 1]


def enforce_intent(
    intent: Intent,
    *,
    user_text: str,
    context: GroundingContext,
    locale: str = "en",
    clarifications_asked: int = 0,
) -> GuardrailOutcome:
    """Ground an intent and apply the refusal, bound, and language guardrails.

    ``clarifications_asked`` is the number of clarifying questions already asked
    earlier in the exchange, counted from the conversation history. At the MQ-001
    bound the refusal becomes terminal: the request is declined, no further question
    is asked, and ``constraints`` is marked so the client can offer catalogue search
    and human support.
    """

    grounded, report = ground_intent(intent, user_text=user_text, context=context)
    flags = set(report.flags)
    citations = report.citations

    if grounded.intent_type == NON_COMMAND_INTENT_TYPE:
        # A greeting or other non-command message is answered conversationally: it
        # sets no payment field, asks no clarifying question, and is never a coverage
        # miss. The client renders the reply from this intent (MQ-001).
        grounded = replace(
            grounded,
            target=None,
            amount=None,
            reference=None,
            clarifying_question=None,
        )
        flags.add("non_command")
        return GuardrailOutcome(intent=grounded, flags=frozenset(flags), citations=citations)

    language_fallback = False
    note: str | None = None
    detected = grounded.detected_language
    if detected is not None and detected not in SUPPORTED_LANGUAGES:
        flags.add("unsupported_language")
        language_fallback = True
        note = LANGUAGE_FALLBACK_NOTE

    unresolved = (
        grounded.confidence < INTENT_CONFIDENCE_THRESHOLD
        or bool(flags & {"ungrounded_target", "ungrounded_amount", "unresolved"})
        or (grounded.intent_type in PAYMENT_INTENT_TYPES and grounded.target is None)
    )

    limit_reached = unresolved and clarifications_asked >= CLARIFICATION_LIMIT

    if limit_reached:
        # The bound is reached while the request is still unresolved: decline it,
        # ask no further question, and mark it for catalogue search and human support.
        flags.add("clarification_limit_reached")
        grounded = replace(
            grounded,
            intent_type="unknown",
            clarifying_question=None,
            constraints={**grounded.constraints, CLARIFICATION_LIMIT_KEY: True},
        )
    elif unresolved:
        flags.add(
            "low_confidence" if grounded.confidence < INTENT_CONFIDENCE_THRESHOLD else "unresolved"
        )
        if grounded.intent_type in PAYMENT_INTENT_TYPES:
            grounded = replace(grounded, intent_type="unknown")
        grounded = replace(
            grounded,
            clarifying_question=normalize_question(grounded.clarifying_question),
        )
    elif grounded.clarifying_question is not None:
        # A resolved request keeps at most one question, and only if the model set one.
        grounded = replace(
            grounded, clarifying_question=normalize_question(grounded.clarifying_question)
        )

    if language_fallback and not limit_reached and grounded.clarifying_question is None:
        grounded = replace(
            grounded, clarifying_question=normalize_question(DEFAULT_CLARIFYING_QUESTION)
        )

    if language_fallback and note:
        flags.add("language_note")

    return GuardrailOutcome(
        intent=grounded,
        flags=frozenset(flags),
        citations=citations,
        language_fallback=language_fallback,
        note=note,
    )


# --- Composition guardrails ------------------------------------------------------


@dataclass(frozen=True)
class CompositionValidation:
    """The result of validating a declarative UI stream against the catalogue."""

    ok: bool
    errors: tuple[str, ...] = ()
    component_names: tuple[str, ...] = ()


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        found: list[str] = []
        for item in value.values():
            found.extend(_walk_strings(item))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(_walk_strings(item))
        return found
    return []


def _component_names(message: Mapping[str, Any]) -> list[str]:
    """Extract component names from the shapes the client catalogue uses."""

    names: list[str] = []
    candidates = message.get("components")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        candidates = []

    def from_entry(entry: Any) -> str | None:
        if isinstance(entry, str):
            return entry
        if isinstance(entry, Mapping):
            for key in ("component", "componentName", "type", "name"):
                value = entry.get(key)
                if isinstance(value, str):
                    return value
            # A nested component object under a "component" key.
            nested = entry.get("component")
            if isinstance(nested, Mapping):
                for key in ("componentName", "type", "name"):
                    value = nested.get(key)
                    if isinstance(value, str):
                        return value
        return None

    for entry in candidates:
        name = from_entry(entry)
        if name:
            names.append(name)

    # createSurface may carry a root component directly.
    root = from_entry(message.get("root"))
    if root:
        names.append(root)
    return names


def validate_composition(
    messages: Sequence[Mapping[str, Any]],
    *,
    allowed_components: frozenset[str] | None = None,
) -> CompositionValidation:
    """Validate a UI stream: known message types, catalogue components, no code."""

    allowed = allowed_components
    errors: list[str] = []
    names: list[str] = []

    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return CompositionValidation(ok=False, errors=("messages must be an array",))

    for index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            errors.append(f"message {index} is not an object")
            continue
        message_type = message.get("type")
        if message_type not in COMPOSITION_MESSAGE_TYPES:
            errors.append(f"message {index} has unknown type {message_type!r}")
            continue
        for text in _walk_strings(message):
            lowered = text.lower()
            if any(pattern in lowered for pattern in _EXECUTABLE_PATTERNS):
                errors.append(f"message {index} contains executable content")
                break
            if _EXTERNAL_LOAD_RE.search(text):
                errors.append(f"message {index} contains an external resource load")
                break
        for name in _component_names(message):
            names.append(name)
            if allowed is not None and name not in allowed:
                errors.append(f"message {index} requests unknown component {name!r}")

    return CompositionValidation(ok=not errors, errors=tuple(errors), component_names=tuple(names))
