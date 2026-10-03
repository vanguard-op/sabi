"""C-017..C-019: payment authorisation, execution, and listing.

Paths are declared without the ``/v1`` prefix; the payment application mounts
this router under it, exactly as the API and AI services discover their module
routers (DELIVERY.md, conventions). The API gateway authenticates the account
owner and resolves the service to its collecting body before forwarding, so the
trusted context arrives as headers (see :mod:`deps`). Rate limiting is a gateway
concern and is not repeated here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query

from sabi_payments.core.errors import PaymentError
from sabi_payments.payments.deps import (
    LimitDep,
    PayeeDep,
    ServiceDep,
    ServiceTypeDep,
    UserDep,
)
from sabi_payments.payments.schemas import (
    AuthoriseRequest,
    AuthoriseResponse,
    ExecuteRequest,
    ExecuteResponse,
    PaymentListResponse,
    PaymentSummary,
)

router = APIRouter(tags=["payments"])

_PAYMENT_STATUSES = frozenset(
    {"initiated", "authorized", "pending", "succeeded", "failed", "reversed", "refunded"}
)
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


@router.post("/payments/authorise", status_code=201, response_model=AuthoriseResponse)
def authorise(
    request: AuthoriseRequest,
    payments: ServiceDep,
    user_id: UserDep,
    payee: PayeeDep,
    limit: LimitDep,
    kind: ServiceTypeDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuthoriseResponse:
    result = payments.authorise(
        user_id=user_id,
        service_id=request.service_id,
        amount=request.amount,
        currency=request.currency,
        payee=payee,
        payee_reference=request.payee_reference,
        payment_method_id=request.payment_method_id,
        channel=request.channel,
        second_confirmation=request.second_confirmation,
        idempotency_key=idempotency_key,
        authorisation_limit=limit,
        service_type=kind,
    )
    return AuthoriseResponse(
        payment_id=result.payment_id,
        status=result.status,
        mandate_id=result.mandate_id,
        rail_reference=result.rail_reference,
    )


@router.post("/payments/{paymentId}/execute", response_model=ExecuteResponse)
def execute(
    paymentId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: ExecuteRequest,
    payments: ServiceDep,
    user_id: UserDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExecuteResponse:
    result = payments.execute(
        user_id=user_id,
        payment_id=paymentId,
        mandate_id=request.mandate_id,
        idempotency_key=idempotency_key or "",
    )
    return ExecuteResponse(
        payment_id=result.payment_id,
        status=result.status,
        rail_reference=result.rail_reference,
    )


@router.get("/payments", response_model=PaymentListResponse)
def list_payments(
    payments: ServiceDep,
    user_id: UserDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    status: str | None = Query(default=None),
) -> PaymentListResponse:
    if status is not None and status not in _PAYMENT_STATUSES:
        raise PaymentError(400, "invalid_request", "That payment status is not valid.")
    effective_limit = max(1, min(limit, _MAX_LIMIT))
    page = payments.list_payments(
        user_id=user_id, cursor=cursor, limit=effective_limit, status=status
    )
    return PaymentListResponse(
        payments=[
            PaymentSummary(
                payment_id=payment.id,
                service_id=payment.service_id,
                amount=payment.amount,
                currency=payment.currency,
                payee=payment.payee,
                status=payment.status,
                channel=payment.channel,
                created_at=payment.created_at,
                updated_at=payment.updated_at,
            )
            for payment in page.payments
        ],
        next_cursor=page.next_cursor,
    )


__all__ = ["router"]
