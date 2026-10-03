"""Case lifecycle: states, service windows, and escalation (FEAT-009).

operations.md defines a per-type service window while a case is with the
provider, and requires a case that exceeds it to escalate rather than sit open
silently. The scheduler that calls this runs with the payment loop; the rules
themselves are pure so they are testable without a clock, a queue, or a running
payment service.

Business-day arithmetic skips weekends. No public-holiday calendar is available
at launch, so a window that straddles a holiday resolves a day early, which is
the safe direction: the case is escalated, not left waiting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db.models import PaymentCase

# Service windows per case type (operations.md, "Support model and service
# windows"). Breaching one escalates to the payment partner.
SERVICE_WINDOW_BUSINESS_DAYS: dict[str, int] = {
    "failed_no_delivery": 3,
    "refund": 5,
    "disputed": 7,
    "receipt_missing": 2,
}

# The case state machine (operations.md). Transitions are explicit so a closed
# case is terminal and an escalated case can still be resolved by the partner.
CASE_STATUSES = frozenset({"open", "awaiting_provider", "resolved", "escalated", "closed"})

ALLOWED_CASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"awaiting_provider", "escalated", "resolved"}),
    "awaiting_provider": frozenset({"resolved", "escalated"}),
    "escalated": frozenset({"resolved"}),
    "resolved": frozenset({"closed"}),
    "closed": frozenset(),
}

# A case is being worked while in one of these states; a resolved or closed case
# has cleared its condition.
ACTIVE_CASE_STATUSES = frozenset({"open", "awaiting_provider", "escalated"})


@dataclass(frozen=True, slots=True)
class WindowBreach:
    """The window a case has exceeded, with the deadline that passed."""

    case_id: str
    case_type: str
    deadline: datetime


def service_window_days(case_type: str) -> int | None:
    """The documented service window for a case type, in business days."""
    return SERVICE_WINDOW_BUSINESS_DAYS.get(case_type)


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_CASE_TRANSITIONS.get(current, frozenset())


def _as_utc(value: datetime) -> datetime:
    """Put a datetime on the UTC timeline, reading a naive one as UTC.

    SQLite returns a naive datetime for a ``DateTime(timezone=True)`` column
    even though the escalation job's clock is aware, so comparing the two
    directly raises. A naive value is taken as UTC; an aware value already
    carries its instant and is left as-is, which keeps the PostgreSQL path
    unchanged.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def add_business_days(start: datetime, days: int) -> datetime:
    """Advance by business days, skipping Saturday and Sunday."""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def window_deadline(case: PaymentCase) -> datetime | None:
    """When the case's service window closes, or None for an unknown type."""
    days = service_window_days(case.type)
    if days is None:
        return None
    return add_business_days(_as_utc(case.opened_at), days)


def exceeds_service_window(case: PaymentCase, now: datetime) -> bool:
    """Whether an active case is past its window and should escalate."""
    if case.status not in ACTIVE_CASE_STATUSES:
        return False
    deadline = window_deadline(case)
    return deadline is not None and _as_utc(now) >= deadline


def find_breaches(cases: list[PaymentCase], now: datetime) -> list[WindowBreach]:
    """The active cases past their window, for escalation and notification."""
    breaches: list[WindowBreach] = []
    for case in cases:
        if not exceeds_service_window(case, now):
            continue
        deadline = window_deadline(case)
        if deadline is None:  # pragma: no cover - guarded by exceeds_service_window
            continue
        breaches.append(WindowBreach(case_id=case.id, case_type=case.type, deadline=deadline))
    return breaches


__all__ = [
    "ACTIVE_CASE_STATUSES",
    "ALLOWED_CASE_TRANSITIONS",
    "CASE_STATUSES",
    "SERVICE_WINDOW_BUSINESS_DAYS",
    "WindowBreach",
    "add_business_days",
    "can_transition",
    "exceeds_service_window",
    "find_breaches",
    "service_window_days",
    "window_deadline",
]
