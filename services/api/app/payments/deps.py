"""FastAPI dependency wiring for the gateway payment module."""

from __future__ import annotations

from fastapi import Request

from app.payments.client import PaymentModuleClient


def get_payment_client(request: Request) -> PaymentModuleClient:
    """The process-wide payment module client, built by the app factory.

    Exposed as a dependency so a test can substitute a deterministic double via
    ``app.dependency_overrides`` without a running payment module.
    """

    return request.app.state.payment_module_client
