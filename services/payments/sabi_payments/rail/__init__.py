"""Concrete payment-rail adapters behind the ``core.rail.RailPort`` port.

The module's state machine, mandate check, and audit trail depend only on the
port, never on a partner SDK (architecture.md, "Payment Module"). This package
holds the adapters:

- :class:`~sabi_payments.rail.mock.MockRail` is the mock/sandbox rail used while
  the licensed partner is deferred and for the synthetic probe that measures the
  execution path (NFR-004, NFR-011). It simulates the three documented outcomes
  without moving real money.
- :func:`~sabi_payments.rail.factory.build_rail` selects the configured adapter.
  The licensed rail is added there when it lands; callers keep taking a
  ``RailPort`` and never change (D-027).
"""

from __future__ import annotations

from sabi_payments.rail.factory import build_rail
from sabi_payments.rail.mock import MockRail, MockScenario
from sabi_payments.rail.settings import RailSettings, get_rail_settings

__all__ = [
    "MockRail",
    "MockScenario",
    "RailSettings",
    "build_rail",
    "get_rail_settings",
]
