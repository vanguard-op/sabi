"""Gateway payment endpoints (C-017..C-019; FEAT-005).

The gateway is the client's single entry point (architecture.md, "API Gateway /
Backend-for-Frontend"). These routes enforce the authenticated account-owner
session and the module rate limit, validate the contract bounds and resolve the
trusted context, then forward the call to the isolated payment module, which
owns authorisation, execution, and the payment store. The response body is the
module's, unchanged: the gateway neither reshapes nor fabricates it.

Auth and errors are the frozen contract: a missing session is 401; an invalid
amount, currency, channel, service, or missing mandate and idempotency key are
400 with the shared envelope; rate limiting is 429. The module's own refusals
travel back through the boundary with their status and code intact, including a
duplicate authorisation's 409 carrying the existing payment. A payment module
that cannot be reached is 503 with ``payment_unavailable``, since the gateway
has no grounded result of its own to give.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_rate_limiter
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData
from app.db.session import get_db
from app.payments import service
from app.payments.client import PaymentModuleClient
from app.payments.deps import get_payment_client
from app.payments.schemas import (
    AuthoriseRequest,
    AuthoriseResponse,
    ExecuteRequest,
    ExecuteResponse,
    PaymentListResponse,
)

router = APIRouter(tags=["payments"])

AccountOwner = Annotated[SessionData, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Payments = Annotated[PaymentModuleClient, Depends(get_payment_client)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


@router.post("/payments/authorise", status_code=201, response_model=AuthoriseResponse)
def authorise(
    payload: AuthoriseRequest,
    session: AccountOwner,
    db: DbSession,
    payments: Payments,
    limiter: Limiter,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    # Limit before validation so a burst of malformed requests cannot outrun it.
    limiter.check(f"payments:authorise:{session.user_id}")

    command = service.AuthoriseCommand(
        service_id=payload.service_id,
        amount=payload.amount,
        currency=payload.currency,
        payee_reference=payload.payee_reference,
        payment_method_id=(payload.payment_method_id or None),
        channel=payload.channel,
        second_confirmation=payload.second_confirmation,
    )
    service_id = service.validate_authorise(command)

    context = service.resolve_service(db, service_id)
    context = replace(context, user_id=session.user_id)
    key = (idempotency_key or "").strip() or None
    return payments.authorise(
        context=context,
        body=service.authorise_body(command),
        idempotency_key=key,
    )


@router.post("/payments/{paymentId}/execute", response_model=ExecuteResponse)
def execute(
    paymentId: str,  # noqa: N803  (contract path placeholder is camelCase)
    payload: ExecuteRequest,
    session: AccountOwner,
    payments: Payments,
    limiter: Limiter,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    limiter.check(f"payments:execute:{session.user_id}")

    mandate_id = service.require_mandate(payload.mandate_id)
    key = service.require_idempotency_key(idempotency_key)

    # An execution forwards the payment's already-resolved context: the module
    # reads the payee and service type from the payment it holds, and the
    # mandate is verified against that stored amount and payee. The gateway
    # forwards the account owner and defers to the module for the rest.
    context = service.owner_context(session.user_id)
    return payments.execute(
        context=context,
        payment_id=paymentId,
        body={"mandateId": mandate_id},
        idempotency_key=key,
    )


@router.get("/payments", response_model=PaymentListResponse)
def list_payments(
    session: AccountOwner,
    payments: Payments,
    limiter: Limiter,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=service.DEFAULT_LIMIT),
    status: str | None = Query(default=None),
) -> dict:
    limiter.check(f"payments:list:{session.user_id}")

    resolved_cursor, effective_limit, resolved_status = service.list_query(
        cursor=cursor, limit=limit, status=status
    )
    # A read needs no payee or service type; the module scopes it to the owner.
    context = service.owner_context(session.user_id)
    return payments.list_payments(
        context=context,
        cursor=resolved_cursor,
        limit=effective_limit,
        status=resolved_status,
    )


__all__ = ["router"]
