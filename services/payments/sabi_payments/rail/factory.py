"""Select the configured rail adapter.

This is the swap seam. The module hands the factory's result to
``PaymentService`` as a ``RefundRailPort``; adding the licensed partner means
adding a branch here and reading its credentials from the secret store, with no
change to the state machine, the mandate check, or any HTTP caller (D-027).

A ``disabled`` backend returns ``DisabledRefundRail``: it invents nothing and
reports an unknown outcome for both a charge and a refund, so a payment is held
pending rather than fabricated as settled while no licensed rail is wired
(FEAT-005, FEAT-009).
"""

from __future__ import annotations

from sabi_payments.rail.disabled import DisabledRefundRail
from sabi_payments.rail.mock import MockRail, MockScenario
from sabi_payments.rail.port import RefundRailPort
from sabi_payments.rail.settings import RailSettings, get_rail_settings


def build_rail(settings: RailSettings | None = None) -> RefundRailPort:
    """Build the rail adapter the deployment is configured for.

    The returned adapter carries both boundaries: the charge port the execution
    path already used, and the refund port FEAT-009 needs. A disabled backend
    still returns an adapter, so a refund reports an unknown outcome rather than
    crashing on a missing method.
    """
    resolved = settings or get_rail_settings()
    backend = resolved.resolved_backend()
    if backend == "mock":
        return MockRail(
            default_scenario=MockScenario(resolved.mock_default_scenario),
            reference_prefix=resolved.mock_reference_prefix,
        )
    return DisabledRefundRail()


__all__ = ["build_rail"]
