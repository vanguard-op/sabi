"""Everyday bill payment flows (FEAT-007, C-033–C-035).

Rules this module owns, from features.md FEAT-007 and user-flow Flow 3:

- A payment is prevented when the biller is offline; no debit occurs (alternate
  path B). Validation reports the reason before anything is authorised.
- A prepaid token is returned and stored with the receipt (acceptance
  criterion 1). The token endpoint holds a succeeded payment open and retries
  retrieval rather than marking it complete without the token (alternate C).
- An airtime purchase records the recipient and amount and makes a receipt
  available (acceptance criterion 2).
- A duplicate authorisation executes once and returns the first payment; the
  Idempotency-Key is the dedupe key (FEAT-007, DELIVERY.md conventions).
- The biller and the isolated payment module are reached through
  :mod:`app.bills.ports`; this service never touches the payment store.

The recipient identifier is treated as personal data: it is stored only on the
captured receipt's payment through the payment module, never written to logs.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.bills import repository
from app.bills.ports import (
    BILLER_UNAVAILABLE,
    BillerPort,
    BillPaymentPort,
    BillPaymentResult,
)
from app.bills.schemas import (
    BillPaymentResponse,
    BillRangeOut,
    BillTokenResponse,
    BillValidateResponse,
)
from app.core.errors import APIError, ErrorCode
from app.db.models import Service
from app.payments_port import PaymentLookup
from app.receipts import service as receipts_service

# A bill is settled in Naira (schema.md, Payment.currency).
_CURRENCY = "NGN"

# A token that has not arrived is retried rather than failing the payment; the
# client is told how long to wait before checking again (C-035).
AWAITING_TOKEN_STATUS = "awaiting_token"
TOKEN_RETRY_AFTER_SECONDS = 3

# The daily-bill payment channel for this API surface.
_CHANNEL = "app"


# --------------------------------------------------------------------------- #
# C-033: validate
# --------------------------------------------------------------------------- #
def validate(
    db: Session,
    biller: BillerPort,
    *,
    service_id: str,
    recipient: str,
    amount: int | None,
) -> BillValidateResponse:
    """Check a recipient, and optionally an amount, before paying."""
    identifier = recipient.strip()
    if not identifier or not _has_alphanumeric(identifier):
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter a valid account or number to pay.")
    if amount is not None and amount <= 0:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter an amount greater than zero.")

    service = repository.get_service(db, service_id)
    if service is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that service.")

    _require_biller_online(biller, service_id)

    result = biller.validate(service_id=service_id, recipient=identifier, amount=amount)
    known_amount = result.known_amount if result.known_amount is not None else service.known_amount
    return BillValidateResponse(
        valid=result.valid,
        recipient_identifier=identifier,
        known_amount=known_amount,
        currency=result.currency or service.currency,
        range=(
            BillRangeOut(minimum=result.amount_range.minimum, maximum=result.amount_range.maximum)
            if result.amount_range is not None
            else None
        ),
        reason=result.reason,
    )


# --------------------------------------------------------------------------- #
# C-034: pay
# --------------------------------------------------------------------------- #
def pay(
    db: Session,
    biller: BillerPort,
    payment_port: BillPaymentPort,
    *,
    user_id: str,
    service_id: str,
    recipient: str,
    amount: int,
    currency: str,
    idempotency_key: str | None,
) -> BillPaymentResponse:
    """Authorise and execute one bill, then store its proof."""
    if not idempotency_key or not idempotency_key.strip():
        raise APIError(400, ErrorCode.INVALID_REQUEST, "A payment needs an Idempotency-Key header.")
    key = idempotency_key.strip()

    identifier = recipient.strip()
    if not identifier or not _has_alphanumeric(identifier):
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter a valid account or number to pay.")
    if amount <= 0:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter an amount greater than zero.")
    if currency != _CURRENCY:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Payments are settled in Naira.")

    service = repository.get_service(db, service_id)
    if service is None:
        # C-034 folds an unusable service into invalid input; there is no 404
        # branch on this endpoint.
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That service cannot be paid.")

    _require_biller_online(biller, service_id)

    # Validate before authorising so a wrong account is caught before any debit
    # (user-flow Flow 3 alternate A; feature edge case "wrong meter number").
    check = biller.validate(service_id=service_id, recipient=identifier, amount=amount)
    if not check.valid:
        raise APIError(
            400,
            ErrorCode.INVALID_REQUEST,
            check.reason or "That account was not found.",
        )

    result = payment_port.pay(
        user_id=user_id,
        service_id=service_id,
        payee=service.collecting_body,
        recipient=identifier,
        amount=amount,
        currency=currency,
        channel=_CHANNEL,
        idempotency_key=key,
    )
    receipt_id = _capture_proof(
        db,
        user_id=user_id,
        service=service,
        result=result,
    )
    return BillPaymentResponse(
        payment_id=result.payment_id,
        status=result.status,
        token=result.token,
        receipt_id=receipt_id,
    )


# --------------------------------------------------------------------------- #
# C-035: token
# --------------------------------------------------------------------------- #
def get_token(
    db: Session,
    lookup: PaymentLookup,
    *,
    user_id: str,
    payment_id: str,
) -> BillTokenResponse:
    """Return a bill's token, or report that it is still arriving."""
    payment = lookup.get(user_id=user_id, payment_id=payment_id)
    if payment is None:
        # An unknown payment and another account's payment read as the same 404.
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that payment.")

    receipt = repository.get_token_receipt(db, payment_id=payment.payment_id, user_id=user_id)
    if receipt is not None and receipt.document_ref.strip():
        return BillTokenResponse(token=receipt.document_ref, receipt_id=receipt.id)

    # The payment has not produced its token yet: hold it open and let the
    # client check back rather than marking it complete without the token
    # (FEAT-007, user-flow Flow 3 alternate C).
    return BillTokenResponse(
        status=AWAITING_TOKEN_STATUS,
        retry_after_seconds=TOKEN_RETRY_AFTER_SECONDS,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _require_biller_online(biller: BillerPort, service_id: str) -> None:
    if biller.health(service_id=service_id) == "unavailable":
        raise APIError(
            503,
            BILLER_UNAVAILABLE,
            "This biller is offline right now. Your payment was not started; try again shortly.",
        )


def _capture_proof(
    db: Session,
    *,
    user_id: str,
    service: Service,
    result: BillPaymentResult,
) -> str | None:
    """Store the token or confirmation beside the payment (FEAT-007).

    A token product captures a ``token`` receipt whose document reference is the
    token itself. Any other successful bill captures a ``biller_confirmation``;
    its reference is the rail reference when the rail answered, otherwise the
    proof is stored pending and the client is told not to discard the reference
    (FEAT-008). Nothing is captured for a payment that did not execute.
    """
    if result.status not in {"succeeded", "pending"}:
        return None
    if result.receipt_id:
        return result.receipt_id
    if result.token:
        receipt = receipts_service.capture_receipt(
            db,
            payment_id=result.payment_id,
            user_id=user_id,
            kind="token",
            document_ref=result.token,
            verification_status="verified",
        )
    else:
        receipt = receipts_service.capture_receipt(
            db,
            payment_id=result.payment_id,
            user_id=user_id,
            kind="biller_confirmation",
            document_ref=result.reference or "",
            verification_status="pending",
        )
    return receipt.id


def _has_alphanumeric(value: str) -> bool:
    return any(character.isalnum() for character in value)


__all__ = [
    "AWAITING_TOKEN_STATUS",
    "TOKEN_RETRY_AFTER_SECONDS",
    "get_token",
    "pay",
    "validate",
]
