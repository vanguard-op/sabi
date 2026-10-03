"""Wire models for payment case management (C-026 to C-029).

Field names are camelCase on the wire (DELIVERY.md, conventions). Request models
validate shape only; the cross-record rules (ownership, duplicate dispute,
refundability) live in ``app.cases.service`` so they return the contract's error
envelope. Timestamps render as RFC 3339 UTC.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.time import to_rfc3339
from app.db.models import PaymentCase

# The case service window and owner are owned by operations.md; the wire carries
# the assignee role as a plain string, matching schema.md.
SUPPORT_OPERATIONS_ROLE = "support_operations_agent"

CASE_STATUSES = frozenset({"open", "awaiting_provider", "resolved", "escalated", "closed"})


class CaseSummaryOut(BaseModel):
    """One case in the user's list (C-026)."""

    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(alias="caseId")
    payment_id: str = Field(alias="paymentId")
    type: str
    status: str
    opened_at: str = Field(alias="openedAt")
    updated_at: str = Field(alias="updatedAt")


class CaseListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cases: list[CaseSummaryOut]
    next_cursor: str | None = Field(alias="nextCursor")


class PaymentSummaryOut(BaseModel):
    """The payment behind a case (C-027), mirroring C-019's PaymentSummary."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(alias="paymentId")
    service_id: str = Field(alias="serviceId")
    amount: int
    currency: str
    payee: str
    status: str
    channel: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class PaymentEventOut(BaseModel):
    """One entry in the append-only case timeline, mirroring schema.md."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    payment_id: str = Field(alias="paymentId")
    status: str
    actor: str
    detail: str | None
    occurred_at: str = Field(alias="occurredAt")
    created_at: str = Field(alias="createdAt")


class CaseOut(BaseModel):
    """The full case record (C-027), mirroring schema.md ``PaymentCase``."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    payment_id: str = Field(alias="paymentId")
    user_id: str = Field(alias="userId")
    type: str
    status: str
    assignee_role: str = Field(alias="assigneeRole")
    opened_at: str = Field(alias="openedAt")
    updated_at: str = Field(alias="updatedAt")
    resolved_at: str | None = Field(default=None, alias="resolvedAt")


class CaseDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    case: CaseOut
    payment: PaymentSummaryOut
    timeline: list[PaymentEventOut]


class DisputeRequest(BaseModel):
    """C-028 dispute submission."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=2000)


class DisputeResponse(BaseModel):
    """C-028 result: the newly opened dispute case."""

    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(alias="caseId")
    status: str
    opened_at: str = Field(alias="openedAt")


class RefundRequest(BaseModel):
    """C-029 refund submission. The idempotency key arrives as a header."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=2000)


class RefundResponse(BaseModel):
    """C-029 result. Status is ``reversed`` or ``refunded``."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(alias="paymentId")
    status: str
    refund_reference: str | None = Field(default=None, alias="refundReference")


def case_summary(case: PaymentCase) -> CaseSummaryOut:
    return CaseSummaryOut(
        case_id=case.id,
        payment_id=case.payment_id,
        type=case.type,
        status=case.status,
        opened_at=to_rfc3339(case.opened_at),
        updated_at=to_rfc3339(case.updated_at),
    )


def case_record(case: PaymentCase) -> CaseOut:
    return CaseOut(
        id=case.id,
        payment_id=case.payment_id,
        user_id=case.user_id,
        type=case.type,
        status=case.status,
        assignee_role=case.assignee_role,
        opened_at=to_rfc3339(case.opened_at),
        updated_at=to_rfc3339(case.updated_at),
        resolved_at=to_rfc3339(case.resolved_at) if case.resolved_at else None,
    )


__all__ = [
    "CASE_STATUSES",
    "SUPPORT_OPERATIONS_ROLE",
    "CaseDetailResponse",
    "CaseListResponse",
    "CaseOut",
    "CaseSummaryOut",
    "DisputeRequest",
    "DisputeResponse",
    "PaymentEventOut",
    "PaymentSummaryOut",
    "RefundRequest",
    "RefundResponse",
    "case_record",
    "case_summary",
]
