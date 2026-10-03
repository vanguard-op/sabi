"""Everyday bill payment endpoints (C-033–C-035; FEAT-007).

Paths are declared without the ``/v1`` prefix; the application factory mounts
the router under it (DELIVERY.md, conventions). Every route needs an
authenticated account-owner session and is scoped to that owner.

The biller and the isolated payment module are reached through the boundary in
``app.bills.ports``; when either is not wired the endpoint reports the matching
degraded state (biller offline/503, payments unavailable/503) rather than
inventing a validated recipient, a payment, or a token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.bills import service
from app.bills.ports import (
    BillerPort,
    BillPaymentPort,
    PaymentLookup,
    get_biller,
    get_payment_lookup,
    get_payment_port,
)
from app.bills.schemas import (
    BillPaymentRequest,
    BillPaymentResponse,
    BillTokenResponse,
    BillValidateRequest,
    BillValidateResponse,
)
from app.core.sessions import SessionData
from app.db.session import get_db

router = APIRouter(tags=["bills"])

AccountOwner = Annotated[SessionData, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Biller = Annotated[BillerPort, Depends(get_biller)]
Payments = Annotated[BillPaymentPort, Depends(get_payment_port)]
PaymentReader = Annotated[PaymentLookup, Depends(get_payment_lookup)]


@router.post("/payments/bills/validate", response_model=BillValidateResponse)
def validate_bill(
    payload: BillValidateRequest,
    session: AccountOwner,
    db: DbSession,
    biller: Biller,
) -> BillValidateResponse:
    return service.validate(
        db,
        biller,
        service_id=payload.service_id,
        recipient=payload.recipient_identifier,
        amount=payload.amount,
    )


@router.post("/payments/bills", status_code=201, response_model=BillPaymentResponse)
def pay_bill(
    payload: BillPaymentRequest,
    session: AccountOwner,
    db: DbSession,
    biller: Biller,
    payments: Payments,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BillPaymentResponse:
    return service.pay(
        db,
        biller,
        payments,
        user_id=session.user_id,
        service_id=payload.service_id,
        recipient=payload.recipient_identifier,
        amount=payload.amount,
        currency=payload.currency,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/payments/bills/{paymentId}/token",
    response_model=BillTokenResponse,
    response_model_exclude_none=True,
    responses={
        200: {"description": "The token was issued and is stored with its receipt."},
        202: {"description": "The payment settled; the token has not arrived yet."},
        409: {"description": "The payment failed; no token will be issued."},
    },
)
def get_bill_token(
    paymentId: str,  # noqa: N803  (contract path placeholder is camelCase)
    response: Response,
    session: AccountOwner,
    db: DbSession,
    lookup: PaymentReader,
) -> BillTokenResponse | Response:
    result = service.get_token(db, lookup, user_id=session.user_id, payment_id=paymentId)
    if result.status == service.FAILED_STATUS:
        # A terminal failure has no token and must not be polled; return the
        # contract's 409 body so the client opens the FEAT-009 failure/refund
        # path instead of waiting on ``awaiting_token`` (C-035). Emitted
        # verbatim so ``reason`` is present as ``null`` when none was recorded.
        return JSONResponse(
            status_code=409,
            content={"status": result.status, "reason": result.reason},
        )
    # A token that has not arrived is an accepted, still-in-progress state; the
    # client retries after ``retryAfterSeconds`` (C-035).
    if result.status is not None:
        response.status_code = 202
    return result
