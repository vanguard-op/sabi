"""FastAPI dependencies for the payment surface.

The module sits behind the API gateway, which authenticates the account owner and
resolves the service to its collecting body before forwarding. Identity and the
resolved payee therefore arrive as trusted headers, not from the client body; a
missing identity is 401, matching the gateway's contract for C-017..C-019. The
module performs no session authentication of its own (architecture.md).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from sabi_payments.core.config import PaymentSettings
from sabi_payments.core.errors import PaymentError
from sabi_payments.payments.service import PaymentService


def get_settings(request: Request) -> PaymentSettings:
    return request.app.state.settings


def get_payment_service(request: Request) -> PaymentService:
    return request.app.state.payment_service


def current_user_id(x_sabi_user_id: str | None = Header(default=None)) -> str:
    """The authenticated account owner forwarded by the gateway."""
    if not x_sabi_user_id or not x_sabi_user_id.strip():
        raise PaymentError(401, "unauthenticated", "Sign in to continue.")
    return x_sabi_user_id.strip()


def resolved_payee(x_sabi_payee: str | None = Header(default=None)) -> str:
    """The collecting body the gateway resolved for the service."""
    if not x_sabi_payee or not x_sabi_payee.strip():
        raise PaymentError(400, "invalid_request", "This service has no collecting body.")
    return x_sabi_payee.strip()


def authorisation_limit(
    x_sabi_authorisation_limit: str | None = Header(default=None),
) -> int | None:
    if x_sabi_authorisation_limit is None or not x_sabi_authorisation_limit.strip():
        return None
    try:
        value = int(x_sabi_authorisation_limit)
    except ValueError:
        raise PaymentError(
            400, "invalid_request", "The authorisation limit is not valid."
        ) from None
    return value if value >= 0 else None


def service_type(x_sabi_service_type: str | None = Header(default=None)) -> str:
    value = (x_sabi_service_type or "bill").strip().lower()
    return value if value in {"government", "bill"} else "bill"


ServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
UserDep = Annotated[str, Depends(current_user_id)]
PayeeDep = Annotated[str, Depends(resolved_payee)]
LimitDep = Annotated[int | None, Depends(authorisation_limit)]
ServiceTypeDep = Annotated[str, Depends(service_type)]


__all__ = [
    "LimitDep",
    "PayeeDep",
    "ServiceDep",
    "ServiceTypeDep",
    "UserDep",
    "authorisation_limit",
    "current_user_id",
    "get_payment_service",
    "get_settings",
    "resolved_payee",
    "service_type",
]
