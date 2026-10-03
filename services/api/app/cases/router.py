"""Payment case HTTP surface (C-026 to C-029).

Paths are declared without the ``/v1`` prefix; the app factory mounts the router
under it (DELIVERY.md, conventions). Every endpoint needs an authenticated
account-owner session and is scoped to that owner: a case or payment belonging
to another account reads as absent (least privilege). The case list is
rate-limited like the other list surfaces; the case detail and the two write
actions are not, so a user tracking a failed payment is never throttled out of
their own status (FEAT-009).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_rate_limiter
from app.cases import service
from app.cases.ports import get_payment_lookup, get_refund_port
from app.cases.schemas import (
    CaseDetailResponse,
    CaseListResponse,
    DisputeRequest,
    DisputeResponse,
    RefundRequest,
    RefundResponse,
)
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData
from app.db.session import get_db
from app.payments_port import PaymentLookup, RefundPort

router = APIRouter(tags=["cases"])

AccountOwner = Annotated[SessionData, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]
PaymentReader = Annotated[PaymentLookup, Depends(get_payment_lookup)]
Refunder = Annotated[RefundPort, Depends(get_refund_port)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


@router.get("/cases", response_model=CaseListResponse)
def list_cases(
    session: AccountOwner,
    db: DbSession,
    limiter: Limiter,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    status: str | None = Query(default=None),
) -> CaseListResponse:
    # Limit before validation so a burst of malformed requests cannot outrun it.
    limiter.check(f"cases:list:{session.user_id}")
    return service.list_user_cases(
        db,
        user_id=session.user_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.get("/cases/{caseId}", response_model=CaseDetailResponse)
def get_case(
    caseId: str,  # noqa: N803  (contract path placeholder is camelCase)
    session: AccountOwner,
    db: DbSession,
    lookup: PaymentReader,
) -> CaseDetailResponse:
    return service.get_user_case(
        db,
        lookup,
        user_id=session.user_id,
        case_id=caseId,
    )


@router.post("/cases/{caseId}/dispute", status_code=201, response_model=DisputeResponse)
def dispute_case(
    caseId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: DisputeRequest,
    session: AccountOwner,
    db: DbSession,
) -> DisputeResponse:
    return service.open_dispute(
        db,
        user_id=session.user_id,
        case_id=caseId,
        reason=request.reason,
    )


@router.post("/payments/{paymentId}/refund", status_code=202, response_model=RefundResponse)
def refund_payment(
    paymentId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: RefundRequest,
    session: AccountOwner,
    db: DbSession,
    lookup: PaymentReader,
    refund_port: Refunder,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RefundResponse:
    return service.request_refund(
        db,
        lookup,
        refund_port,
        user_id=session.user_id,
        payment_id=paymentId,
        reason=request.reason,
        idempotency_key=idempotency_key,
    )
