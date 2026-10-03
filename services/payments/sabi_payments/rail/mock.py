"""Mock/sandbox rail adapter.

The licensed payment partner is deferred (D-027, R-004), so execution runs
against an in-process sandbox that moves no real money. It implements the same
``RailPort`` the state machine already calls, so swapping in the licensed
partner later is a change at the factory, not at any caller.

The mock reproduces the outcomes the product documents for the rail, because the
execution path's behaviour is defined by them (FEAT-005):

- ``succeeded`` with an opaque transaction reference;
- ``failed`` with a reason and no partial debit, including the insufficient-funds
  refusal the service surfaces as 402;
- ``pending`` for a timeout with unknown outcome, which the service holds for
  reconciliation and never retries blindly.

It is deterministic: a replay of the same idempotency key returns the same
reference, matching the rail's own idempotency contract.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from sabi_payments.core.rail import RailCharge, RailOutcome

_DECLINE_REASON = "The collecting body declined this payment."
_INSUFFICIENT_FUNDS_REASON = "Insufficient funds for this payment."
_UNKNOWN_REASON = "The payment rail did not confirm the outcome."


class MockScenario(StrEnum):
    """The outcome the sandbox rail returns for a charge.

    ``SUCCESS`` is the default so a development payment completes end to end;
    the other scenarios exist so the failure and unknown paths are exercised
    against the same adapter rather than a bespoke test double (FEAT-005).
    """

    SUCCESS = "success"
    DECLINE = "decline"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    UNKNOWN = "unknown"


class MockRail:
    """A deterministic, in-process sandbox rail.

    The scenario is fixed for the adapter's lifetime; a synthetic probe or a
    focused test uses :meth:`enqueue` to make the next charge answer differently
    and then falls back to the default. Every charge is recorded so a probe can
    confirm what the rail was asked to do. Nothing here logs or stores a
    credential; a charge carries only the payment facts already held by the
    module.
    """

    def __init__(
        self,
        default_scenario: MockScenario = MockScenario.SUCCESS,
        *,
        reference_prefix: str = "SBX",
    ) -> None:
        self._default_scenario = default_scenario
        self._reference_prefix = reference_prefix.strip() or "SBX"
        self._queued: list[MockScenario] = []
        self.charges: list[RailCharge] = []

    @property
    def default_scenario(self) -> MockScenario:
        return self._default_scenario

    def enqueue(self, scenario: MockScenario) -> None:
        """Make the next charge answer with ``scenario``, one shot."""
        self._queued.append(scenario)

    def health(self) -> str:
        """Report liveness for the synthetic authorization probe (NFR-011).

        The sandbox is always reachable; this is what a real rail adapter would
        report from its own health check.
        """
        return "healthy"

    def charge(self, request: RailCharge) -> RailOutcome:
        self.charges.append(request)
        scenario = self._queued.pop(0) if self._queued else self._default_scenario
        if request.amount <= 0:
            # Defense in depth: the service refuses a non-positive amount before
            # execution, but the rail must never acknowledge a debit of nothing.
            return RailOutcome(status="failed", failure_reason=_DECLINE_REASON)
        if scenario is MockScenario.SUCCESS:
            return RailOutcome(status="succeeded", reference=self._reference(request))
        if scenario is MockScenario.INSUFFICIENT_FUNDS:
            return RailOutcome(status="failed", failure_reason=_INSUFFICIENT_FUNDS_REASON)
        if scenario is MockScenario.DECLINE:
            return RailOutcome(status="failed", failure_reason=_DECLINE_REASON)
        return RailOutcome(status="pending", failure_reason=_UNKNOWN_REASON)

    def _reference(self, request: RailCharge) -> str:
        # Opaque and deterministic: the same idempotency key and payment yield
        # the same reference, so a replayed charge is never a second debit.
        material = f"{request.idempotency_key}:{request.payment_id}".encode()
        digest = hashlib.sha256(material).hexdigest()[:20].upper()
        return f"{self._reference_prefix}-{digest}"


__all__ = ["MockRail", "MockScenario"]
