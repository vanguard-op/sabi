"""Federal government payment flow rules (FEAT-006, C-030 to C-032).

Rules this module owns, from features.md FEAT-006 and user-flow Flow 2:

- A federal obligation is paid through a collection channel. A service that is
  not a government service, or has no collection channel, is not a federal
  collection and cannot be prepared here.
- When the agency has switched its collection account the channel reads as
  ``changed`` and a prepare is a conflict until it is re-resolved, so a payment
  is never sent to a stale account (FEAT-006, alternate G).
- An obligation that requires a payer reference is not paid without one; the
  prepare explains how to obtain it instead (FEAT-006, Flow 2 step 6).
- A succeeded federal payment carries the FTeR once the central platform issues
  it; until then the receipt endpoint reports ``awaiting_receipt`` and the client
  keeps checking (FEAT-006, alternate F).
- When the rail confirms but the agency record does not, a reconciliation case
  is opened against the reference; a second case for the same payment is a
  conflict (FEAT-006; operations.md, "Reconciliation operations").
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import APIError, ErrorCode
from app.db.models import Receipt
from app.federal import repository
from app.federal.models import FederalCollection
from app.federal.ports import FederalReceiptSource, PaymentLookup
from app.federal.schemas import (
    FederalPrepareResponse,
    FederalReceiptResponse,
    FederalReconcileResponse,
)
from app.receipts.service import capture_receipt

# A succeeded federal payment whose FTeR has not arrived yet. The value is a
# poll hint for the client; it is not a promise the receipt is coming now
# (FEAT-006, alternate F).
AWAITING_RECEIPT_STATUS = "awaiting_receipt"
RECEIPT_RETRY_SECONDS = 30

# The official e-receipt stored against a federal obligation (schema.md,
# Receipt.kind); a federal payment carries exactly this proof.
FEDERAL_RECEIPT_KIND = "official_e_receipt"

# A reconciliation against the agency record is worked by the reconciliation
# officer (operations.md, "Reconciliation operations").
RECONCILIATION_OFFICER_ROLE = "reconciliation_officer"


def prepare_obligation(
    db: Session,
    *,
    service_id: str,
    payer_reference: str | None,
) -> FederalPrepareResponse:
    service = repository.get_service(db, service_id)
    if service is None:
        # An unknown service id is a malformed request rather than a disclosure
        # of which service ids exist (contract C-030: 400, invalid service).
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That service is not valid.")

    collection = repository.get_collection(db, service.id)
    if service.type != "government" or collection is None:
        raise APIError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "This service is not a federal government collection.",
        )

    if collection.status == "changed":
        # The agency has moved the collection account; the user must re-resolve
        # the obligation so Sabi pays the current channel (FEAT-006, alternate G).
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "The agency's collection account has changed. Re-resolve the obligation.",
        )

    return FederalPrepareResponse(
        service_id=service.id,
        collecting_body=service.collecting_body,
        amount=service.known_amount,
        currency=service.currency,
        requires_reference=collection.requires_reference,
        instructions=_instructions(collection, payer_reference),
    )


def _instructions(collection: FederalCollection, payer_reference: str | None) -> str | None:
    """What the payer needs to know before authorising.

    A required reference that has not been supplied is the one case that must be
    explained rather than paid around; otherwise the channel's general guidance
    applies (FEAT-006, Flow 2 step 6).
    """
    if collection.requires_reference and not (payer_reference or "").strip():
        return collection.reference_instructions or collection.instructions
    return collection.instructions


def get_federal_receipt(
    db: Session,
    lookup: PaymentLookup,
    source: FederalReceiptSource,
    *,
    user_id: str,
    payment_id: str,
) -> FederalReceiptResponse:
    payment = lookup.get(user_id=user_id, payment_id=payment_id)
    if payment is None:
        # A payment owned by another account is a 404, never a 403, so the
        # endpoint does not confirm someone else's payment exists.
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that payment.")

    if payment.status != "succeeded":
        # The FTeR only exists once the obligation is settled; any other state
        # is a conflict (contract C-031: 409, payment did not succeed).
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "This payment has not succeeded, so no official receipt is available.",
        )

    fter = source.fetch(payment_id=payment.payment_id, reference=payment.reference)
    if fter is None:
        # The central platform has not issued the receipt yet. The payment is
        # kept and the client keeps checking; nothing is fabricated
        # (FEAT-006, alternate F).
        return FederalReceiptResponse(
            status=AWAITING_RECEIPT_STATUS,
            retry_after_seconds=RECEIPT_RETRY_SECONDS,
        )

    stored = capture_receipt(
        db,
        payment_id=payment.payment_id,
        user_id=user_id,
        kind=FEDERAL_RECEIPT_KIND,
        receipt_number=fter.receipt_number,
        verification_status=fter.verification_status,
        document_ref=fter.document_ref or "",
        issued_at=fter.issued_at,
    )
    return _receipt_response(stored)


def _receipt_response(stored: Receipt) -> FederalReceiptResponse:
    return FederalReceiptResponse(
        receipt_id=stored.id,
        receipt_number=stored.receipt_number,
        verification_status=stored.verification_status,
    )


def open_reconciliation(
    db: Session,
    lookup: PaymentLookup,
    *,
    user_id: str,
    payment_id: str,
    reason: str,
) -> FederalReconcileResponse:
    payment = lookup.get(user_id=user_id, payment_id=payment_id)
    if payment is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that payment.")

    # One reconciliation per payment: a second open case for the same payment is
    # a conflict, and the existing case and its evidence are preserved
    # (FEAT-006; operations.md, "Reconciliation operations").
    if repository.find_open_reconciliation(db, payment_id) is not None:
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "A reconciliation for this payment is already open.",
        )

    case = repository.create_reconciliation_case(
        db,
        payment_id=payment.payment_id,
        user_id=user_id,
        reason=reason,
        assignee_role=RECONCILIATION_OFFICER_ROLE,
    )
    return FederalReconcileResponse(case_id=case.id, status=case.status)


__all__ = [
    "AWAITING_RECEIPT_STATUS",
    "FEDERAL_RECEIPT_KIND",
    "RECEIPT_RETRY_SECONDS",
    "RECONCILIATION_OFFICER_ROLE",
    "get_federal_receipt",
    "open_reconciliation",
    "prepare_obligation",
]
