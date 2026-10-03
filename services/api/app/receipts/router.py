"""Receipt retrieval endpoints (C-023–C-025; FEAT-008).

Paths are declared without the ``/v1`` prefix; the application factory mounts the
router under it (DELIVERY.md, conventions). Every route is the authenticated
account owner's own history: a receipt owned by another account is a 404, never a
403, so the endpoint does not confirm that someone else's receipt exists.

A receipt view reads its payment fields across the isolated store boundary; when
that store is not wired the lookup reports ``payment_unavailable`` (503) rather
than returning a receipt with fabricated fields, the same degraded boundary the
rail uses.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_rate_limiter
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData
from app.db.session import get_db
from app.receipts import service
from app.receipts.deps import get_payment_lookup
from app.payments_port import PaymentLookup
from app.receipts.schemas import (
    ReceiptDetailResponse,
    ReceiptDocumentResponse,
    ReceiptListResponse,
)

router = APIRouter(tags=["receipts"])

AccountOwner = Annotated[SessionData, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Lookup = Annotated[PaymentLookup, Depends(get_payment_lookup)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


@router.get("/receipts", response_model=ReceiptListResponse)
def list_receipts(
    session: AccountOwner,
    db: DbSession,
    lookup: Lookup,
    limiter: Limiter,
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=service.DEFAULT_LIMIT),
) -> ReceiptListResponse:
    limiter.check(f"receipts:list:{session.user_id}")
    return service.list_receipts(
        db,
        lookup,
        user_id=session.user_id,
        query=q,
        cursor=cursor,
        limit=limit,
    )


@router.get("/receipts/{receiptId}", response_model=ReceiptDetailResponse)
def get_receipt(
    receiptId: str,  # noqa: N803  (contract path placeholder is camelCase)
    session: AccountOwner,
    db: DbSession,
    lookup: Lookup,
) -> ReceiptDetailResponse:
    return service.get_receipt(db, lookup, user_id=session.user_id, receipt_id=receiptId)


@router.get("/receipts/{receiptId}/document", response_model=ReceiptDocumentResponse)
def get_receipt_document(
    receiptId: str,  # noqa: N803  (contract path placeholder is camelCase)
    session: AccountOwner,
    db: DbSession,
) -> ReceiptDocumentResponse:
    return service.get_document(db, user_id=session.user_id, receipt_id=receiptId)
