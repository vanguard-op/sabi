"""Payment case workflow (FEAT-009, C-026 to C-029).

Rules this module owns, from features.md and operations.md:

- A case is scoped to its owner; a case id from another account reads as absent.
- A dispute is opened once per payment: a second dispute is a conflict, and the
  existing receipt and events are preserved, never rewritten (FEAT-008).
- A refund is keyed by the payment reference and the idempotency key; a second
  refund for the same payment is blocked before the rail is asked (FEAT-009).
- Only a succeeded payment can move to ``reversed``/``refunded``, matching the
  payment state machine. Any other state is not refundable.
- The payment store is read through its port; if it cannot be reached the case
  view degrades with ``payment_unavailable`` rather than inventing a record.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.cases import repository
from app.cases.schemas import (
    CASE_STATUSES,
    SUPPORT_OPERATIONS_ROLE,
    CaseDetailResponse,
    CaseListResponse,
    DisputeResponse,
    PaymentEventOut,
    PaymentSummaryOut,
    RefundResponse,
    case_record,
    case_summary,
)
from app.core.errors import APIError, ErrorCode
from app.core.time import to_rfc3339
from app.payments_port import (
    PaymentEventView,
    PaymentLookup,
    PaymentView,
    RefundPort,
    RefundView,
)

# Only a settled payment can be reversed or refunded (payment state machine).
REFUNDABLE_PAYMENT_STATES = frozenset({"succeeded"})
TERMINAL_REFUND_STATES = frozenset({"reversed", "refunded"})

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def list_user_cases(
    db: Session,
    *,
    user_id: str,
    status: str | None,
    cursor: str | None,
    limit: int | None,
) -> CaseListResponse:
    if status is not None and status not in CASE_STATUSES:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That case status is not recognised.")

    effective_limit = _clamp_limit(limit)
    cases, next_cursor = repository.list_cases(
        db,
        user_id=user_id,
        status=status,
        cursor=cursor,
        limit=effective_limit,
    )
    return CaseListResponse(
        cases=[case_summary(case) for case in cases],
        next_cursor=next_cursor,
    )


def get_user_case(
    db: Session,
    lookup: PaymentLookup,
    *,
    user_id: str,
    case_id: str,
) -> CaseDetailResponse:
    case = repository.get_case(db, case_id, user_id=user_id)
    if case is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that case.")

    # The lookup is user-scoped, so a cross-account payment reads as absent; an
    # unwired store raises payment_unavailable from the port, never a fabricated
    # payment (FEAT-009).
    payment = lookup.get(user_id=user_id, payment_id=case.payment_id)
    if payment is None:
        raise _payment_unavailable()
    events = lookup.events(user_id=user_id, payment_id=case.payment_id)

    return CaseDetailResponse(
        case=case_record(case),
        payment=_payment_summary(payment),
        timeline=[_payment_event(event) for event in events],
    )


def open_dispute(
    db: Session,
    *,
    user_id: str,
    case_id: str,
    reason: str,
) -> DisputeResponse:
    case = repository.get_case(db, case_id, user_id=user_id)
    if case is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that case.")

    # One dispute per payment: the original payment and its receipt are
    # preserved and only the case record is added (FEAT-008, FEAT-009).
    if repository.find_dispute_for_payment(db, case.payment_id) is not None:
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "A dispute for this payment is already open.",
        )

    dispute = repository.create_case(
        db,
        payment_id=case.payment_id,
        user_id=case.user_id,
        case_type="disputed",
        status="open",
        assignee_role=SUPPORT_OPERATIONS_ROLE,
    )
    # ``reason`` is user-supplied and may carry personal data; it stays in the
    # case workflow and is not written to the auth audit log or application logs.
    case.updated_at = dispute.opened_at
    return DisputeResponse(
        case_id=dispute.id,
        status=dispute.status,
        opened_at=to_rfc3339(dispute.opened_at),
    )


def request_refund(
    db: Session,
    lookup: PaymentLookup,
    refund_port: RefundPort,
    *,
    user_id: str,
    payment_id: str,
    reason: str,
    idempotency_key: str | None,
) -> RefundResponse:
    # Money movements carry an Idempotency-Key (DELIVERY.md, conventions); a
    # missing or blank key is a malformed request, not a silent retry.
    if not idempotency_key or not idempotency_key.strip():
        raise APIError(400, ErrorCode.INVALID_REQUEST, "A refund needs an Idempotency-Key header.")
    key = idempotency_key.strip()

    # The user-scoped lookup answers an unknown payment and another user's
    # payment with the same None, so the endpoint does not reveal which payment
    # ids exist (least privilege).
    payment = lookup.get(user_id=user_id, payment_id=payment_id)
    if payment is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that payment.")

    if payment.status in TERMINAL_REFUND_STATES:
        raise _duplicate_refund()
    if payment.status not in REFUNDABLE_PAYMENT_STATES:
        raise APIError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "This payment cannot be refunded in its current state.",
        )

    # Block the second refund before asking the rail (FEAT-009, operations.md).
    if repository.find_open_refund_for_payment(db, payment.payment_id) is not None:
        raise _duplicate_refund()

    result = refund_port.refund(
        user_id=user_id,
        payment_id=payment.payment_id,
        reason=reason,
        idempotency_key=key,
    )
    _assert_refund_settled(result)

    # A refund case tracks the request to rail or biller acknowledgement, and is
    # opened exactly once per refund (operations.md).
    repository.create_case(
        db,
        payment_id=payment.payment_id,
        user_id=user_id,
        case_type="refund",
        status="awaiting_provider",
        assignee_role=SUPPORT_OPERATIONS_ROLE,
    )

    return RefundResponse(
        payment_id=payment.payment_id,
        status=result.status,
        refund_reference=result.refund_reference,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(limit, _MAX_LIMIT))


def _payment_summary(payment: PaymentView) -> PaymentSummaryOut:
    return PaymentSummaryOut(
        payment_id=payment.payment_id,
        service_id=payment.service_id,
        amount=payment.amount,
        currency=payment.currency,
        payee=payment.payee,
        status=payment.status,
        channel=payment.channel,
        created_at=to_rfc3339(payment.created_at),
        updated_at=to_rfc3339(payment.updated_at),
    )


def _payment_event(event: PaymentEventView) -> PaymentEventOut:
    return PaymentEventOut(
        id=event.event_id,
        payment_id=event.payment_id,
        status=event.status,
        actor=event.actor,
        detail=event.detail,
        occurred_at=to_rfc3339(event.occurred_at),
        created_at=to_rfc3339(event.created_at),
    )


def _assert_refund_settled(result: RefundView) -> None:
    if result.status not in TERMINAL_REFUND_STATES:
        raise _payment_unavailable()


def _duplicate_refund() -> APIError:
    return APIError(
        409,
        ErrorCode.CONFLICT,
        "A refund for this payment has already been requested.",
    )


def _payment_unavailable() -> APIError:
    return APIError(
        503,
        ErrorCode.PAYMENT_UNAVAILABLE,
        "Payment records are unavailable right now. Try again shortly.",
    )


__all__ = [
    "REFUNDABLE_PAYMENT_STATES",
    "TERMINAL_REFUND_STATES",
    "get_user_case",
    "list_user_cases",
    "open_dispute",
    "request_refund",
]
