"""Wire the aggregator adapter into the channel gateway's ports.

The gateway reaches identity, payments, and SMS delivery through ports bound on
``app.state`` (see :mod:`app.channels.ports`). This module builds the
aggregator-backed SMS delivery port and binds it, so a deployment that fronts
the gateway with a real aggregator gets C-038 delivery reporting without
touching the gateway module.

Binding is deliberately conservative: an existing ``channels_sms`` port wins, so
a test or a different deployment can substitute its own boundary and this call
is a no-op. The pooled HTTP client is exposed on ``app.state`` so the
application's lifespan can close it; until the app factory calls
:func:`bind_aggregator`, the gateway falls back to its own unavailable
boundary, exactly as it does for every other unwired port.

The inbound USSD callback is translation only (see
:mod:`app.channels.aggregator.callback`); the gateway's mounted C-036/C-037
surface remains the one contract, and the deployment feeds it the parsed fields.
"""

from __future__ import annotations

from typing import Any

from app.channels.aggregator.client import AggregatorClient, AggregatorEndpoint
from app.channels.aggregator.sms import AggregatorSmsDeliveryPort

# The app.state key the gateway reads its SMS boundary from; kept in step with
# app.channels.ports.get_sms_delivery.
SMS_PORT_STATE_KEY = "channels_sms"
# The app.state key holding the pooled client, for the application's shutdown.
CLIENT_STATE_KEY = "channels_aggregator_client"


def build_sms_delivery_port(settings: Any) -> AggregatorSmsDeliveryPort:
    """Build the aggregator-backed SMS port and its client."""

    client = AggregatorClient(AggregatorEndpoint.from_settings(settings))
    return AggregatorSmsDeliveryPort(client=client)


def bind_aggregator(app: Any, settings: Any) -> None:
    """Bind the aggregator SMS port on ``app.state`` unless one is already set.

    The client is exposed at ``app.state.channels_aggregator_client`` so the
    application's shutdown can close it; binding does not replace an existing
    SMS boundary, so tests keep their in-memory stand-in.
    """

    if getattr(app.state, SMS_PORT_STATE_KEY, None) is not None:
        return
    port = build_sms_delivery_port(settings)
    app.state.channels_sms = port
    setattr(app.state, CLIENT_STATE_KEY, port.client)


__all__ = [
    "CLIENT_STATE_KEY",
    "SMS_PORT_STATE_KEY",
    "bind_aggregator",
    "build_sms_delivery_port",
]
