"""Guardrails the quality contract requires before output reaches a user.

These are product decisions enforced in code, not left to the implementer:

* Refusal: below the confidence threshold the assistant asks a follow-up question in
  its model-authored ``reply``, building on the earlier turns, up to three in one
  conversation, and never presents a payment intent; at the bound it declines instead
  of asking again (MQ-001).
* Non-command: a greeting or small talk is classified ``non_command``, which carries
  no payment field, asks no clarifying question, and is never a coverage miss (MQ-001).
* No invention: grounding drops an identifier, amount, or reference the model could
  not trace (see :mod:`core.grounding`).
* Reply boundaries: the model-authored ``reply`` carries no executable code and no
  URLs, and it states no amount or service identifier that is not in the grounded
  context. A reply that breaks a boundary is dropped to null so the client renders
  its prewritten fallback; its wording is never edited or pinned (MQ-001, MQ-004).
* Language: a detected language that is not enabled is flagged and noted rather than
  mis-resolved (MQ-004); the reply's language is bound into the prompt, not fixed here.
* Composition: the composed surface is an A2UI message stream validated against the
  published catalog in :mod:`core.a2ui`, the agent-side pre-send phase; no private
  component-name copy lives here (MQ-003).

Nothing here raises for a merely imperfect model answer; it either repairs the
sequence or marks it unresolved so the caller can ask, decline, or render a fallback.
Tone and category-neutrality are prompt-enforced and judged by the reply rubric, not
deterministically rewritten here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from core.config import INTENT_CONFIDENCE_CUTOFF
from core.grounding import GroundingContext, amount_is_traceable, ground_intent
from core.history import CLARIFICATION_LIMIT, CLARIFICATION_LIMIT_KEY
from core.schemas import (
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

# The internal note raised when the detected language is not enabled yet (MQ-004).
# It is a signal for telemetry, never appended to the reply: the reply's wording is
# the model's and is not post-processed. The prompt binds the request locale as the
# language to reply in, so an unsupported detection degrades to the served locale.
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

# A currency-marked amount stated in a reply, e.g. "₦5,000", "NGN 5000", "5,000
# naira", or "500000 kobo". Only an explicit currency marker is treated as a stated
# fact, so an ordinal ("three questions") or a confidence ("0.70") is never mistaken
# for one.
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?:₦|ngn\s*|naira\s*)(\d[\d,]*(?:\.\d+)?)"
    r"|(\d[\d,]*(?:\.\d+)?)\s*(?:naira|kobo|ngn)\b",
    re.IGNORECASE,
)
# A catalogue service identifier quoted in prose, e.g. "svc-landuse". Replies should
# not carry raw identifiers, but if one appears it must be grounded.
_SERVICE_ID_RE = re.compile(r"\bsvc-[a-z0-9][a-z0-9-]*\b", re.IGNORECASE)

# The default question used by capabilities that still hold a structured clarifying
# question (the payment-intent extraction). It is not part of the MQ-001 intent
# contract, where the model authors the question inside ``reply``.
DEFAULT_CLARIFYING_QUESTION = "Which service or biller do you want to pay?"


def normalize_question(question: str | None) -> str:
    """Return exactly one question from possibly several.

    Shared by the structured-question capabilities; the MQ-001 reply path does not
    normalise wording, so this is not applied to a model-authored reply.
    """

    if not question or not question.strip():
        return DEFAULT_CLARIFYING_QUESTION
    text = question.strip()
    end = text.find("?")
    if end == -1:
        return text.rstrip(".! ") + "?"
    return text[: end + 1]


@dataclass(frozen=True)
class GuardrailOutcome:
    """The intent and reply after guardrails, with flags explaining any repair."""

    intent: Intent
    reply: str | None = None
    flags: frozenset[str] = frozenset()
    citations: tuple[str, ...] = ()
    language_fallback: bool = False
    note: str | None = None


def _reply_amount_grounded(value: int, context: GroundingContext, user_text: str) -> bool:
    """True when a currency-marked amount in a reply traces to a grounded source.

    An amount is grounded when it is in the retrieved data, the user stated it (a
    confirmation of the user's own amount is legitimate), or it is the naira/kobo
    counterpart of a grounded amount, since the catalogue holds integer kobo while a
    reply may display naira.
    """

    if amount_is_traceable(value, user_text=user_text, context=context):
        return True
    if value and value * 100 in context.amounts:
        return True
    return value % 100 == 0 and value // 100 in context.amounts


def enforce_reply(
    reply: str | None, *, context: GroundingContext, user_text: str = ""
) -> tuple[str | None, frozenset[str]]:
    """Apply the reply boundaries: safety and grounding, never wording.

    The model phrases the reply freely, so it is neither rewritten nor normalised.
    A reply that carries executable code, a URL, or an ungrounded amount or service
    identifier is dropped to null: the client renders its prewritten fallback for the
    state, and no blank or unsafe turn reaches the user (MQ-001). Tone and
    category-neutrality are prompt-enforced and judged by the reply rubric, not
    rewritten here.
    """

    if reply is None:
        return None, frozenset()
    text = reply.strip()
    if not text:
        return None, frozenset({"empty_reply"})

    lowered = text.lower()
    unsafe = any(pattern in lowered for pattern in _EXECUTABLE_PATTERNS)
    if unsafe or _EXTERNAL_LOAD_RE.search(text):
        # Executable content or a URL is never allowed in a reply.
        return None, frozenset({"unsafe_reply"})

    for match in _CURRENCY_AMOUNT_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw is None:
            continue
        try:
            value = int(raw.replace(",", "").split(".")[0])
        except ValueError:  # pragma: no cover - the regex guarantees digits
            continue
        if not _reply_amount_grounded(value, context, user_text):
            # A stated amount that is not in the retrieved data is an invented fact.
            return None, frozenset({"ungrounded_reply"})

    for match in _SERVICE_ID_RE.finditer(text):
        if match.group(0) not in context.service_ids:
            return None, frozenset({"ungrounded_reply"})

    return text, frozenset()


def enforce_intent(
    intent: Intent,
    *,
    user_text: str,
    context: GroundingContext,
    reply: str | None = None,
    locale: str = "en",
    clarifications_asked: int = 0,
) -> GuardrailOutcome:
    """Ground an intent and apply the refusal, bound, language, and reply guardrails.

    ``clarifications_asked`` is the number of clarifying questions already asked
    earlier in the exchange, counted from the conversation history. At the MQ-001
    bound the refusal becomes terminal: the request is declined and ``constraints`` is
    marked so the client can offer catalogue search and human support. The model-
    authored ``reply`` is returned unchanged when it satisfies the boundaries, or as
    null when it does not.
    """

    grounded, report = ground_intent(intent, user_text=user_text, context=context)
    flags = set(report.flags)
    citations = report.citations
    safe_reply, reply_flags = enforce_reply(reply, context=context, user_text=user_text)
    flags |= reply_flags

    if grounded.intent_type == NON_COMMAND_INTENT_TYPE:
        # A greeting or other non-command message is answered conversationally: it
        # sets no payment field and is never a coverage miss. Its reply is authored by
        # the model (MQ-001).
        grounded = replace(grounded, target=None, amount=None, reference=None)
        flags.add("non_command")
        return GuardrailOutcome(
            intent=grounded, reply=safe_reply, flags=frozenset(flags), citations=citations
        )

    language_fallback = False
    note: str | None = None
    detected = grounded.detected_language
    if detected is not None and detected not in SUPPORTED_LANGUAGES:
        flags.add("unsupported_language")
        flags.add("language_note")
        language_fallback = True
        note = LANGUAGE_FALLBACK_NOTE

    unresolved = (
        grounded.confidence < INTENT_CONFIDENCE_THRESHOLD
        or bool(flags & {"ungrounded_target", "ungrounded_amount", "unresolved"})
        or (grounded.intent_type in PAYMENT_INTENT_TYPES and grounded.target is None)
    )

    limit_reached = unresolved and clarifications_asked >= CLARIFICATION_LIMIT

    if limit_reached:
        # The bound is reached while the request is still unresolved: decline it and
        # mark it for catalogue search and human support. The after-bound reply is the
        # model's; no further question is asked through the structured contract.
        flags.add("clarification_limit_reached")
        grounded = replace(
            grounded,
            intent_type="unknown",
            constraints={**grounded.constraints, CLARIFICATION_LIMIT_KEY: True},
        )
    elif unresolved:
        flags.add(
            "low_confidence" if grounded.confidence < INTENT_CONFIDENCE_THRESHOLD else "unresolved"
        )
        if grounded.intent_type in PAYMENT_INTENT_TYPES:
            grounded = replace(grounded, intent_type="unknown")

    return GuardrailOutcome(
        intent=grounded,
        reply=safe_reply,
        flags=frozenset(flags),
        citations=citations,
        language_fallback=language_fallback,
        note=note,
    )


# --- Composition guardrails ------------------------------------------------------
# A composed surface is an A2UI message stream, validated against the published
# catalog in :mod:`core.a2ui` (agent-side pre-send phase) with the client repeating
# the check on receipt (FEAT-011, MQ-003). The unused stream-validation helpers that
# lived here were removed with the server-side component-name copy they relied on.
