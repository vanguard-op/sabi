"""The disabled rail, extended with the refund boundary.

When no licensed rail is wired the charge boundary reports an unknown outcome so
a payment is held pending rather than fabricated as settled (FEAT-005). The
refund boundary must behave the same way: it invents no reversal reference and
claims no money moved back, so the caller reconciles instead of telling a user a
refund settled when it did not (FEAT-009, D-027).

Subclassing ``DisabledRail`` keeps the charge behaviour and identity from the
frozen port module, so a consumer checking for the disabled boundary still
recognises it.
"""

from __future__ import annotations

from sabi_payments.core.rail import DisabledRail
from sabi_payments.rail.port import RailRefund, RailRefundOutcome

_DISABLED_REASON = "The payment rail is not wired into this deployment."


class DisabledRefundRail(DisabledRail):
    """No licensed rail: a refund is an unknown outcome, never a settlement."""

    def refund(self, request: RailRefund) -> RailRefundOutcome:
        return RailRefundOutcome(status="pending", failure_reason=_DISABLED_REASON)


__all__ = ["DisabledRefundRail"]
