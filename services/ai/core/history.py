"""Conversation history carried on the C-009 request.

The client sends the earlier turns of one exchange, oldest first and bounded to six,
so the assistant can build each clarification on the answers already given instead of
restarting. History is untrusted data: the same delimiter neutralisation the
retrieved block uses is applied, and the prompt frames it as data only.

Keeping the model has already asked at most three clarifying questions in a
conversation is enforced from this history, not left to the model: an assistant turn
that is a question is one clarification attempt, and a non-command reply (a
statement) is never counted as one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# C-009 accepts at most six prior turns, oldest first.
MAX_HISTORY_TURNS = 6

# The roles a history turn may carry.
HISTORY_ROLES: frozenset[str] = frozenset({"user", "assistant"})

# MQ-001: at most three clarifying questions may be asked in one conversation.
CLARIFICATION_LIMIT = 3

# Set in the intent's free-form ``constraints`` object when the bound is reached, so
# the client and coverage tooling can tell a declined request from a new question
# without re-deriving it. camelCase to match the wire boundary (D-018).
CLARIFICATION_LIMIT_KEY = "clarificationLimitReached"


@dataclass(frozen=True)
class ConversationTurn:
    """One prior turn of the exchange, oldest first."""

    role: str
    text: str


def clarifying_questions_asked(history: Sequence[ConversationTurn]) -> int:
    """Count the assistant's clarifying questions already asked in this exchange.

    The assistant renders exactly one clarifying question per unresolved turn, and it
    is normalised to end with ``?``. A non-command reply is a statement rendered from
    the intent, not a question, so it is not counted (MQ-001).
    """

    return sum(
        1 for turn in history if turn.role == "assistant" and turn.text.strip().endswith("?")
    )


def render_history(history: Sequence[ConversationTurn]) -> str:
    """Render the prior turns as a delimited, escaped block for the prompt."""

    if not history:
        return "(no earlier turns in this conversation)"
    roles = HISTORY_ROLES
    return "\n".join(
        f"[{turn.role if turn.role in roles else 'user'}] {_neutralise(turn.text)}"
        for turn in history
    )


def _neutralise(value: Any) -> str:
    """Neutralise block delimiters so history cannot close the block early."""

    text = str(value)
    return text.replace("<<<", "< <<").replace(">>>", "> >>")


__all__ = [
    "CLARIFICATION_LIMIT",
    "CLARIFICATION_LIMIT_KEY",
    "HISTORY_ROLES",
    "MAX_HISTORY_TURNS",
    "ConversationTurn",
    "clarifying_questions_asked",
    "render_history",
]
