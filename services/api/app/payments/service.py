"""Gateway rules for the payment endpoints (C-017..C-019).

The gateway owns what the isolated module cannot know: the authenticated account
owner, the service's collecting body, and the limits of its own HTTP surface.
This module holds that policy, kept free of FastAPI so the router stays a thin
adapter and the rules are unit-testable on their own.

What the gateway validates before forwarding:

- the amount is a positive integer and the currency is Naira;
- the channel is one the contract names;
- the service exists and has a collecting body to pay;
- an execution carries a mandate and an idempotency key.

What it deliberately does not decide: whether the amount is above the user's
limit, whether a mandate has expired, and whether a debit can be funded. Those
are the payment module's rules, enforced against its own store, and its answer
travels back through the boundary unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import APIError, ErrorCode
from app.db.models import Service
from app.payments.client import ForwardContext

_CURRENCY = "NGN"
_CHANNELS = frozenset({"app", "ussd", "sms", "whatsapp"})
_SERVICE_TYPES = frozenset({"government", "biller", "merchant"})

# C-019 page bounds, matching the module's own limits.
DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_PAYMENT_STATUSES = frozenset(
    {"initiated", "authorized", "pending", "succeeded", "failed", "reversed", "refunded"}
)


@dataclass(frozen=True, slots=True)
class AuthoriseCommand:
    """The validated C-017 inputs, ready to forward to the module."""

    service_id: str | None
    amount: int
    currency: str
    payee_reference: str | None
    payment_method_id: str | None
    channel: str
    second_confirmation: bool


def resolve_service(db: Session, service_id: str) -> ForwardContext:
    """Resolve a service id to the trusted context the module needs.

    A service that does not exist, or that has no collecting body, is invalid
    input on C-017: the endpoint has no 404 branch, so both fold into 400. The
    ``authorisation_limit`` is left unset because the primary store holds no
    per-user limit yet; the module applies its configured default (FEAT-005).
    """

    service = db.get(Service, service_id)
    collecting_body = (getattr(service, "collecting_body", None) or "").strip()
    if service is None or not collecting_body:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That service cannot be paid.")
    service_type = getattr(service, "type", "") or ""
    if service_type not in _SERVICE_TYPES:
        service_type = "biller"
    return ForwardContext(
        user_id="",  # filled by the router, which owns the session
        payee=collecting_body,
        service_type=service_type,
    )


def owner_context(user_id: str) -> ForwardContext:
    """The context for a call scoped to the account owner alone.

    Execution and listing act on a payment the module already holds, so the
    gateway forwards only the authenticated owner; it does not re-resolve a
    service or invent a payee.
    """
    return ForwardContext(user_id=user_id)


def validate_authorise(command: AuthoriseCommand) -> str:
    """Check the C-017 inputs the contract makes the gateway's to reject.

    Returns the trimmed service id so the caller can resolve it without a
    second None-check.
    """
    if command.amount <= 0:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter an amount greater than zero.")
    if command.currency.upper() != _CURRENCY:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Payments are settled in Naira.")
    if command.channel not in _CHANNELS:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That channel is not supported.")
    service_id = (command.service_id or "").strip()
    if not service_id:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Choose a service to pay.")
    return service_id


def authorise_body(command: AuthoriseCommand) -> dict:
    """The module's request body, carrying only the public contract fields."""
    return {
        "serviceId": (command.service_id or "").strip(),
        "amount": command.amount,
        "currency": command.currency.upper(),
        "payeeReference": command.payee_reference,
        "paymentMethodId": command.payment_method_id,
        "channel": command.channel,
        "secondConfirmation": command.second_confirmation,
    }


def require_mandate(mandate_id: str | None) -> str:
    """C-018 requires a mandate id; a missing one is invalid input."""
    if mandate_id is None or not mandate_id.strip():
        raise APIError(400, ErrorCode.INVALID_REQUEST, "An authorisation is required.")
    return mandate_id.strip()


def require_idempotency_key(idempotency_key: str | None) -> str:
    """Money movements carry an ``Idempotency-Key`` (DELIVERY.md, conventions)."""
    if idempotency_key is None or not idempotency_key.strip():
        raise APIError(400, ErrorCode.INVALID_REQUEST, "A payment needs an Idempotency-Key header.")
    return idempotency_key.strip()


def list_query(
    *, cursor: str | None, limit: int, status: str | None
) -> tuple[str | None, int, str | None]:
    """Normalise the C-019 query: a known status, and a 1..100 page."""
    if status is not None and status != "" and status not in _PAYMENT_STATUSES:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That payment status is not valid.")
    effective_limit = max(1, min(limit, _MAX_LIMIT))
    return (cursor or None), effective_limit, (status or None)


__all__ = [
    "AuthoriseCommand",
    "DEFAULT_LIMIT",
    "authorise_body",
    "list_query",
    "owner_context",
    "require_idempotency_key",
    "require_mandate",
    "resolve_service",
    "validate_authorise",
]
