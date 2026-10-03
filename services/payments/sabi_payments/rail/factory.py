"""Select the configured rail adapter.

This is the swap seam. The module hands the factory's result to
``PaymentService`` as a ``RailPort``; adding the licensed partner means adding a
branch here and reading its credentials from the secret store, with no change to
the state machine, the mandate check, or any HTTP caller (D-027).

A ``disabled`` backend returns ``DisabledRail`` from the port module: it invents
nothing and reports an unknown outcome, so a payment is held pending rather than
fabricated as settled while no licensed rail is wired (FEAT-005, FEAT-009).
"""

from __future__ import annotations

from sabi_payments.core.rail import DisabledRail, RailPort
from sabi_payments.rail.mock import MockRail, MockScenario
from sabi_payments.rail.settings import RailSettings, get_rail_settings


def build_rail(settings: RailSettings | None = None) -> RailPort:
    """Build the rail adapter the deployment is configured for."""
    resolved = settings or get_rail_settings()
    backend = resolved.resolved_backend()
    if backend == "mock":
        return MockRail(
            default_scenario=MockScenario(resolved.mock_default_scenario),
            reference_prefix=resolved.mock_reference_prefix,
        )
    return DisabledRail()


__all__ = ["build_rail"]
