"""Boundary to the licensed payment rail.

The rail is the only component that moves money. Nothing in the module calls a
partner SDK directly: execution goes through this port so the licensed partner
can be swapped without touching the state machine, the mandate check, or the
audit trail (architecture.md, "Payment Module"; D-027).

An unknown outcome is a first-class result, not an error: the rail may accept a
debit and fail before answering, so ``RailOutcome.status`` can be ``pending`` and
the caller holds the payment for reconciliation rather than retrying blindly
(FEAT-005, "Rail timeout with unknown outcome"). A refused execution returns
``failed`` with a reason and no partial debit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RailCharge:
    """One execution request: a single debit for an authorised amount and payee."""

    payment_id: str
    user_id: str
    amount: int
    currency: str
    payee: str
    payee_reference: str | None
    payment_method_id: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RailOutcome:
    """The rail's answer.

    ``status`` is one of ``succeeded``, ``pending`` (unknown outcome), or
    ``failed``. ``reference`` is the rail's transaction reference when it is
    known; ``failure_reason`` is set only for ``failed``.
    """

    status: str
    reference: str | None = None
    failure_reason: str | None = None


class RailPort(Protocol):
    """Execute a charge and report the outcome; no partial debit on failure."""

    def charge(self, request: RailCharge) -> RailOutcome: ...


class DisabledRail:
    """Default when no licensed rail is wired into this deployment.

    Raises nothing and invents nothing: it reports an unknown outcome so the
    payment is held pending and reconciled, which is the documented degraded
    behaviour while the rail is unavailable (FEAT-005; D-027 mock/sandbox rail).
    """

    def charge(self, request: RailCharge) -> RailOutcome:
        return RailOutcome(
            status="pending",
            failure_reason="The payment rail is not wired into this deployment.",
        )


__all__ = ["DisabledRail", "RailCharge", "RailOutcome", "RailPort"]
