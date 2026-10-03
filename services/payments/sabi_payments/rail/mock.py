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

It also serves the refund boundary (FEAT-009): a reversal or refund is keyed by
the debit's reference, so a second refund for a reference the sandbox has already
returned is reported as a duplicate rather than moving money back twice.

It is deterministic: a replay of the same idempotency key returns the same
reference, matching the rail's own idempotency contract.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from sabi_payments.core.rail import RailCharge, RailOutcome
from sabi_payments.rail.port import RailRefund, RailRefundOutcome

_DECLINE_REASON = "The collecting body declined this payment."
_INSUFFICIENT_FUNDS_REASON = "Insufficient funds for this payment."
_UNKNOWN_REASON = "The payment rail did not confirm the outcome."
_REFUND_DECLINE_REASON = "The rail declined this refund."
_REFUND_UNKNOWN_REASON = "The payment rail did not confirm the refund."
_DUPLICATE_REFUND_REASON = "This payment has already been refunded."


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


class MockRefundScenario(StrEnum):
    """The outcome the sandbox rail returns for a refund.

    ``REVERSED`` is the default so a development refund settles end to end and
    the payment reaches a terminal state; ``REFUNDED`` covers a return rather
    than a same-rail reversal, and the other two exercise the unsettled paths
    against the same adapter (FEAT-009).
    """

    REVERSED = "reversed"
    REFUNDED = "refunded"
    DECLINE = "decline"
    UNKNOWN = "unknown"


class MockRail:
    """A deterministic, in-process sandbox rail.

    The scenario is fixed for the adapter's lifetime; a synthetic probe or a
    focused test uses :meth:`enqueue` to make the next charge answer differently
    and then falls back to the default, and :meth:`enqueue_refund` does the same
    for a refund. Every charge and refund is recorded so a probe can confirm what
    the rail was asked to do. A refund is settled at most once per reference:
    the sandbox remembers the references it has returned, so a second refund for
    one is blocked with ``duplicate`` and no second reference is invented.
    Nothing here logs or stores a credential; a request carries only the payment
    facts already held by the module.
    """

    def __init__(
        self,
        default_scenario: MockScenario = MockScenario.SUCCESS,
        *,
        reference_prefix: str = "SBX",
        default_refund_scenario: MockRefundScenario = MockRefundScenario.REVERSED,
    ) -> None:
        self._default_scenario = default_scenario
        self._reference_prefix = reference_prefix.strip() or "SBX"
        self._queued: list[MockScenario] = []
        self._default_refund_scenario = default_refund_scenario
        self._queued_refunds: list[MockRefundScenario] = []
        self.charges: list[RailCharge] = []
        self.refunds: list[RailRefund] = []
        # Reference -> refund reference the sandbox has already returned; the
        # second refund for a reference is blocked here, at the rail boundary.
        self._refunded: dict[str, str] = {}

    @property
    def default_scenario(self) -> MockScenario:
        return self._default_scenario

    @property
    def default_refund_scenario(self) -> MockRefundScenario:
        return self._default_refund_scenario

    def enqueue(self, scenario: MockScenario) -> None:
        """Make the next charge answer with ``scenario``, one shot."""
        self._queued.append(scenario)

    def enqueue_refund(self, scenario: MockRefundScenario) -> None:
        """Make the next refund answer with ``scenario``, one shot."""
        self._queued_refunds.append(scenario)

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

    def refund(self, request: RailRefund) -> RailRefundOutcome:
        self.refunds.append(request)
        key = _refund_key(request)
        # A reference the sandbox already reversed is never refunded twice: the
        # second request is answered with the first refund's reference and a
        # duplicate status the service maps to 409 (FEAT-009; operations.md).
        settled = self._refunded.get(key)
        if settled is not None:
            return RailRefundOutcome(
                status="duplicate",
                refund_reference=settled,
                failure_reason=_DUPLICATE_REFUND_REASON,
            )

        scenario = (
            self._queued_refunds.pop(0) if self._queued_refunds else self._default_refund_scenario
        )
        if scenario in (MockRefundScenario.REVERSED, MockRefundScenario.REFUNDED):
            reference = self._refund_reference(request)
            self._refunded[key] = reference
            return RailRefundOutcome(status=scenario.value, refund_reference=reference)
        if scenario is MockRefundScenario.DECLINE:
            return RailRefundOutcome(status="failed", failure_reason=_REFUND_DECLINE_REASON)
        return RailRefundOutcome(status="pending", failure_reason=_REFUND_UNKNOWN_REASON)

    def _reference(self, request: RailCharge) -> str:
        # Opaque and deterministic: the same idempotency key and payment yield
        # the same reference, so a replayed charge is never a second debit.
        material = f"{request.idempotency_key}:{request.payment_id}".encode()
        digest = hashlib.sha256(material).hexdigest()[:20].upper()
        return f"{self._reference_prefix}-{digest}"

    def _refund_reference(self, request: RailRefund) -> str:
        # Opaque and distinct from the charge reference so the two sides of the
        # movement are told apart in a receipt or a case.
        material = f"refund:{_refund_key(request)}:{request.idempotency_key}".encode()
        digest = hashlib.sha256(material).hexdigest()[:20].upper()
        return f"{self._reference_prefix}-RF-{digest}"


def _refund_key(request: RailRefund) -> str:
    """The reference a refund is keyed by: the rail reference, or the payment id."""
    reference = (request.reference or "").strip()
    return reference or request.payment_id


__all__ = ["MockRail", "MockRefundScenario", "MockScenario"]
