"""USSD session state for the channel gateway (FEAT-010, C-036/C-037).

A USSD session is short and time-bound because session time is billed to the
user's airtime (NFR-006). This module holds the state machine:

    menu -> service -> details -> confirm -> (authorise, C-037) -> result

The session is keyed by the gateway's ``sessionId`` and bound to one MSISDN, so a
session id opened by one number cannot be driven from another (C-036, 409). When
a session times out:

- before authorisation, no payment was executed and the next dial starts fresh;
- after authorisation with the payment still pending, the next dial resumes the
  pending payment rather than restarting it (FEAT-010, alternate path B).

State is process-local and injected as a store so a deployment can back it with
the shared cache; the in-memory store is for development and tests. An MSISDN is
personal data and is held only to resolve the session, never rendered in a
prompt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from app.channels.schemas import (
    STEP_MENU,
    STEP_RESULT,
)
from app.core.ids import new_id
from app.core.time import utcnow

# Payment states that mean an outcome is still to be resolved. A session that
# authorised one of these resumes it on the next dial (FEAT-010).
PENDING_PAYMENT_STATES = frozenset({"pending"})


@dataclass(slots=True)
class UssdSession:
    """One USSD conversation and the payment it may authorise."""

    session_id: str
    msisdn: str
    user_id: str
    locale: str
    step: str = STEP_MENU
    done: bool = False
    # Payment fields captured as the conversation advances.
    service_id: str | None = None
    recipient: str | None = None
    amount: int | None = None
    currency: str = "NGN"
    # Set once C-037 authorises; distinguishes "timed out before" from "after".
    authorised: bool = False
    payment_pending: bool = False
    payment_status: str | None = None
    payment_reference: str | None = None
    # Resume marker: a fresh dial against the same session id reuses this.
    resumed_from: str | None = None
    opened_at: datetime = field(default_factory=utcnow)
    last_seen_at: datetime = field(default_factory=utcnow)
    expires_at: datetime = field(default_factory=utcnow)


class UssdSessionStore(Protocol):
    """Store for short-lived USSD sessions."""

    def get(self, session_id: str) -> UssdSession | None: ...

    def save(self, session: UssdSession) -> None: ...

    def delete(self, session_id: str) -> None: ...


class InMemoryUssdSessionStore:
    """Process-local session store for development and tests. Not for production."""

    def __init__(self) -> None:
        self._sessions: dict[str, UssdSession] = {}

    def get(self, session_id: str) -> UssdSession | None:
        return self._sessions.get(session_id)

    def save(self, session: UssdSession) -> None:
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def open_session(
    *,
    session_id: str,
    msisdn: str,
    user_id: str,
    locale: str,
    timeout_seconds: int,
    clock: Callable[[], datetime] = utcnow,
) -> UssdSession:
    """Create a fresh session at the menu step with a bounded lifetime."""

    now = clock()
    return UssdSession(
        session_id=session_id,
        msisdn=msisdn,
        user_id=user_id,
        locale=locale,
        step=STEP_MENU,
        opened_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=timeout_seconds),
    )


def resume_session(
    previous: UssdSession,
    *,
    session_id: str,
    timeout_seconds: int,
    clock: Callable[[], datetime] = utcnow,
) -> UssdSession:
    """Open a new session that continues a timed-out pending payment.

    The payment fields and the pending marker are carried across so the next
    dial shows the pending result rather than restarting the payment
    (FEAT-010, alternate path B).
    """

    resumed = open_session(
        session_id=session_id,
        msisdn=previous.msisdn,
        user_id=previous.user_id,
        locale=previous.locale,
        timeout_seconds=timeout_seconds,
        clock=clock,
    )
    resumed.service_id = previous.service_id
    resumed.recipient = previous.recipient
    resumed.amount = previous.amount
    resumed.currency = previous.currency
    resumed.authorised = previous.authorised
    resumed.payment_pending = previous.payment_pending
    resumed.payment_status = previous.payment_status
    resumed.payment_reference = previous.payment_reference
    resumed.resumed_from = previous.session_id
    resumed.step = STEP_RESULT if previous.payment_reference else previous.step
    resumed.done = bool(previous.payment_reference)
    return resumed


def is_expired(session: UssdSession, *, clock: Callable[[], datetime] = utcnow) -> bool:
    return session.expires_at <= clock()


def touch(
    session: UssdSession,
    *,
    timeout_seconds: int,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Extend the session on activity without exceeding one lifetime from open."""

    now = clock()
    session.last_seen_at = now
    session.expires_at = min(
        session.opened_at + timedelta(seconds=timeout_seconds),
        now + timedelta(seconds=timeout_seconds),
    )


def new_session_id() -> str:
    return new_id()


__all__ = [
    "PENDING_PAYMENT_STATES",
    "InMemoryUssdSessionStore",
    "UssdSession",
    "UssdSessionStore",
    "is_expired",
    "new_session_id",
    "open_session",
    "resume_session",
    "touch",
]
