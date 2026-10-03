"""Concrete payment-rail adapters behind the rail ports.

The module's state machine, mandate check, and audit trail depend only on the
ports, never on a partner SDK (architecture.md, "Payment Module"). This package
holds the adapters and the refund boundary:

- :class:`~sabi_payments.rail.mock.MockRail` is the mock/sandbox rail used while
  the licensed partner is deferred and for the synthetic probe that measures the
  execution path (NFR-004, NFR-011). It simulates the documented charge and
  refund outcomes without moving real money, and blocks a second refund for a
  reference it has already returned (FEAT-009).
- :class:`~sabi_payments.rail.disabled.DisabledRefundRail` is the disabled
  adapter: both a charge and a refund report an unknown outcome.
- :func:`~sabi_payments.rail.factory.build_rail` selects the configured adapter.
  The licensed rail is added there when it lands; callers keep taking a
  ``RefundRailPort`` and never change (D-027).
- :mod:`~sabi_payments.rail.port` defines the refund request, outcome, and port.
"""

from __future__ import annotations

from sabi_payments.rail.disabled import DisabledRefundRail
from sabi_payments.rail.factory import build_rail
from sabi_payments.rail.mock import MockRail, MockRefundScenario, MockScenario
from sabi_payments.rail.port import RailRefund, RailRefundOutcome, RefundRailPort
from sabi_payments.rail.settings import RailSettings, get_rail_settings

__all__ = [
    "DisabledRefundRail",
    "MockRail",
    "MockRefundScenario",
    "MockScenario",
    "RailRefund",
    "RailRefundOutcome",
    "RailSettings",
    "RefundRailPort",
    "build_rail",
    "get_rail_settings",
]
