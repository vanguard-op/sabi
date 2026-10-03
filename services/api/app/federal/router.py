"""Federal government payment HTTP surface (C-030 to C-032; FEAT-006).

Paths are declared without the ``/v1`` prefix; the application factory mounts the
router under it (DELIVERY.md, conventions). Every endpoint needs an authenticated
account-owner session and is scoped to that owner: a payment belonging to another
account reads as absent, so a guessed payment id cannot expose someone else's
obligation (least privilege).

Two boundaries cross out of the primary store here and are resolved lazily: the
payment record from the isolated payment module, and the Federal Treasury
e-Receipt source. Each has a conservative default, so the monolith boots before
either is wired (see ``app.federal.ports``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.sessions import SessionData
from app.db.session import get_db
from app.federal import service
from app.federal.ports import (
    FederalReceiptSource,
    PaymentLookup,
    get_payment_lookup,
    get_receipt_source,
)
from app.federal.schemas import (
    FederalPrepareRequest,
    FederalPrepareResponse,
    FederalReceiptResponse,
    FederalReconcileRequest,
    FederalReconcileResponse,
)

router = APIRouter(tags=["federal"])

AccountOwner = Annotated[SessionData, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]
PaymentReader = Annotated[PaymentLookup, Depends(get_payment_lookup)]
ReceiptReader = Annotated[FederalReceiptSource, Depends(get_receipt_source)]


@router.post(
    "/payments/federal/prepare",
    response_model=FederalPrepareResponse,
)
def prepare_federal_payment(
    request: FederalPrepareRequest,
    session: AccountOwner,
    db: DbSession,
) -> FederalPrepareResponse:
    """Resolve a federal obligation before the payment is authorised."""
    return service.prepare_obligation(
        db,
        service_id=request.service_id,
        payer_reference=request.payer_reference,
    )


@router.get(
    "/payments/federal/{paymentId}/receipt",
    response_model=FederalReceiptResponse,
    response_model_exclude_none=True,
    responses={
        200: {"description": "The official receipt was retrieved and stored."},
        202: {"description": "The official receipt has not arrived yet."},
    },
)
def get_federal_receipt(
    paymentId: str,  # noqa: N803  (contract path placeholder is camelCase)
    response: Response,
    session: AccountOwner,
    db: DbSession,
    lookup: PaymentReader,
    source: ReceiptReader,
) -> FederalReceiptResponse:
    """Return the stored FTeR, or 202 while the central platform has not issued it."""
    result = service.get_federal_receipt(
        db,
        lookup,
        source,
        user_id=session.user_id,
        payment_id=paymentId,
    )
    if result.status is not None:
        response.status_code = 202
    return result


@router.post(
    "/payments/federal/{paymentId}/reconcile",
    status_code=202,
    response_model=FederalReconcileResponse,
)
def reconcile_federal_payment(
    paymentId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: FederalReconcileRequest,
    session: AccountOwner,
    db: DbSession,
    lookup: PaymentReader,
) -> FederalReconcileResponse:
    """Open a reconciliation against the agency record for a federal payment."""
    return service.open_reconciliation(
        db,
        lookup,
        user_id=session.user_id,
        payment_id=paymentId,
        reason=request.reason,
    )
