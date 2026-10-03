"""Refund boundary, extending the rail port without touching the frozen core.

The charge port lives in :mod:`sabi_payments.core.rail`; this module adds the
reversal/refund operation beside it, so a rail adapter that moves money out also
moves it back through the same swap seam (architecture.md, "Payment Module";
D-027). Callers that execute a debit keep depending on ``RailPort``; callers that
refund depend on :class:`RefundRailPort`, which is that port plus ``refund``.

The result carries the same first-class outcomes as a charge: a settled reversal
or refund names its own reference, an unknown outcome stays pending for
reconciliation, and a second request for a reference the rail already refunded is
reported as ``duplicate`` rather than executed twice (FEAT-009; operations.md,
"Duplicate-refund prevention").

A refund is a return of money for a debit the rail already holds, so it is keyed
by that debit's ``reference``: the reference is what identifies the transaction at
the rail, and the ``idempotency_key`` identifies the caller's attempt to reverse
it. The pair is what makes a retried request safe and a genuinely second refund
detectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sabi_payments.core.rail import RailPort


@dataclass(frozen=True, slots=True)
class RailRefund:
    """One reversal/refund request for a debit the rail has already settled."""

    payment_id: str
    user_id: str
    amount: int
    currency: str
    reference: str | None
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RailRefundOutcome:
    """The rail's answer to a refund.

    ``status`` is ``reversed`` or ``refunded`` when the money has moved back,
    ``pending`` when the outcome is unknown and must be reconciled, ``failed``
    when the rail refused, and ``duplicate`` when this reference was already
    refunded and the request was blocked at the rail boundary.
    """

    status: str
    refund_reference: str | None = None
    failure_reason: str | None = None


class RefundRailPort(RailPort, Protocol):
    """The rail port plus the refund operation.

    Extends ``RailPort`` rather than replacing it, so the state machine and the
    execution path keep taking the charge port unchanged and a complete adapter
    (mock or licensed) satisfies this one.
    """

    def refund(self, request: RailRefund) -> RailRefundOutcome: ...


__all__ = ["RailRefund", "RailRefundOutcome", "RefundRailPort"]
