"""Receipt capture and retrieval (FEAT-008, C-023–C-025).

A receipt is captured when a payment completes and linked to the obligation by
its payment id (FEAT-008). Retrieval joins the receipt in the primary store to
the payment in the isolated store through :mod:`app.receipts.payments`; the
receipt row never changes when a catalogue entry is later edited because the
payment stored its payee and amount at execution time (schema.md, Overview).

Search matches a receipt by reference, agency (payee), or date, as the Receipts
screen asks. Contact between stores is a batch read of the page's payment ids,
so a page costs one lookup rather than one per row.
"""

from __future__ import annotations

import base64
import binascii
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import APIError, ErrorCode
from app.core.time import to_rfc3339
from app.db.models import Receipt
from app.receipts import repository
from app.receipts.payments import PaymentLookup, PaymentView
from app.receipts.schemas import (
    PaymentSummary,
    ReceiptDetailResponse,
    ReceiptDocumentResponse,
    ReceiptListResponse,
    ReceiptOut,
    ReceiptSummary,
)

# A receipt is captured with an empty document reference while the official
# receipt is still being retrieved; the document endpoint reports it as awaiting
# rather than serving a missing file (FEAT-008; user-flow Flow 2, alternate F).
AWAITING_DOCUMENT_REF = ""

# Pagination bounds: the contract default is 20. A search reads a bounded window
# so a query cannot become an unbounded scan across the owner's history.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_SEARCH_SCAN_LIMIT = 500

# Document content type by receipt kind. The schema stores only a reference, not
# a media type; an official e-receipt and a biller confirmation are documents, a
# token is text (schema.md, Receipt.kind).
_CONTENT_TYPES = {
    "official_e_receipt": "application/pdf",
    "biller_confirmation": "application/pdf",
    "token": "text/plain",
}

_CURSOR_PREFIX = "r1."


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #
def capture_receipt(
    db: Session,
    *,
    payment_id: str,
    user_id: str,
    kind: str,
    document_ref: str = AWAITING_DOCUMENT_REF,
    receipt_number: str | None = None,
    verification_status: str = "pending",
    issued_at: datetime | None = None,
) -> Receipt:
    """Store a receipt for a completed payment, or return the existing one.

    A payment can carry more than one kind of proof (an official e-receipt and a
    biller confirmation), so capture is keyed on ``(payment_id, kind)``: a
    repeated capture for the same proof returns the stored record instead of
    duplicating it, which keeps the 100% coverage target from double-counting
    (FEAT-008). The receipt is linked to the obligation by its payment id, the
    only cross-store join.
    """
    existing = _find_by_payment_and_kind(db, payment_id, kind, user_id=user_id)
    if existing is not None:
        return existing

    receipt = Receipt(
        payment_id=payment_id,
        user_id=user_id,
        kind=kind,
        receipt_number=receipt_number,
        verification_status=verification_status,
        document_ref=document_ref,
        issued_at=issued_at,
    )
    db.add(receipt)
    db.flush()
    return receipt


def _find_by_payment_and_kind(
    db: Session, payment_id: str, kind: str, *, user_id: str
) -> Receipt | None:
    return db.execute(
        select(Receipt).where(
            Receipt.payment_id == payment_id,
            Receipt.kind == kind,
            Receipt.user_id == user_id,
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def list_receipts(
    db: Session,
    lookup: PaymentLookup,
    *,
    user_id: str,
    query: str | None,
    cursor: str | None,
    limit: int,
) -> ReceiptListResponse:
    """The owner's receipts, newest first, optionally filtered by ``query``."""
    effective_limit = max(1, min(limit, MAX_LIMIT))
    before = _decode_cursor(cursor)

    if query and query.strip():
        receipts = repository.list_receipts(
            db,
            user_id=user_id,
            limit=effective_limit,
            before=before,
            scan_limit=_SEARCH_SCAN_LIMIT,
        )
        payments = _resolve(lookup, user_id=user_id, receipts=receipts)
        matched = [
            receipt
            for receipt in receipts
            if _matches_query(receipt, payments.get(receipt.payment_id), query)
        ]
        page = matched[:effective_limit]
        # A cursor is only meaningful when more of the scanned window remains.
        has_more = len(matched) > effective_limit or len(receipts) == _SEARCH_SCAN_LIMIT
    else:
        receipts = repository.list_receipts(
            db, user_id=user_id, limit=effective_limit + 1, before=before
        )
        has_more = len(receipts) > effective_limit
        page = receipts[:effective_limit]
        payments = _resolve(lookup, user_id=user_id, receipts=page)

    summaries = [_summary(receipt, payments.get(receipt.payment_id)) for receipt in page]
    next_cursor = _encode_cursor(page[-1]) if has_more and page else None
    return ReceiptListResponse(receipts=summaries, next_cursor=next_cursor)


def _resolve(
    lookup: PaymentLookup, *, user_id: str, receipts: list[Receipt]
) -> dict[str, PaymentView]:
    """Batch-read the payments behind these receipts.

    An empty page touches nothing, so an account with no receipts (or a page with
    none left) still lists successfully when the payment store is not wired.
    """
    if not receipts:
        return {}
    return lookup.get_many(
        user_id=user_id, payment_ids=[receipt.payment_id for receipt in receipts]
    )


def get_receipt(
    db: Session, lookup: PaymentLookup, *, user_id: str, receipt_id: str
) -> ReceiptDetailResponse:
    receipt = repository.get_receipt(db, receipt_id, user_id=user_id)
    if receipt is None:
        # A receipt owned by another account is a 404, never a 403: the
        # existence of another user's receipt is not disclosed.
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that receipt.")
    payment = lookup.get(user_id=user_id, payment_id=receipt.payment_id)
    if payment is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that receipt.")
    return ReceiptDetailResponse(receipt=_receipt_out(receipt), payment=_payment_summary(payment))


def get_document(db: Session, *, user_id: str, receipt_id: str) -> ReceiptDocumentResponse:
    receipt = repository.get_receipt(db, receipt_id, user_id=user_id)
    if receipt is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that receipt.")
    if not (receipt.document_ref or "").strip():
        # The official receipt has not arrived yet; the client keeps checking
        # rather than being handed a broken document (FEAT-008, C-025).
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "This receipt is still being retrieved. Check back shortly.",
        )
    return ReceiptDocumentResponse(
        document_ref=receipt.document_ref,
        content_type=_CONTENT_TYPES.get(receipt.kind, "application/octet-stream"),
        # No share token is minted until the third-party verification surface
        # (FEAT-017) exists; the field is nullable in the contract.
        share_token=None,
    )


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def _matches_query(receipt: Receipt, payment: PaymentView | None, query: str) -> bool:
    needle = query.strip().casefold()
    if not needle:
        return True

    # Reference: the payment's rail reference, its id, or the official receipt
    # number. Never an empty string, so a blank receipt does not match by accident.
    references = [
        value
        for value in (
            payment.reference if payment else None,
            receipt.payment_id,
            receipt.receipt_number,
        )
        if value
    ]
    if any(needle in value.casefold() for value in references):
        return True

    # Agency: the payee stored with the payment.
    if payment is not None and needle in payment.payee.casefold():
        return True

    # Date: an exact calendar day against the source issue date, falling back to
    # the capture date when the source issued no date.
    day = _parse_day(needle)
    if day is not None:
        issued = receipt.issued_at or receipt.created_at
        if issued is not None and issued.date() == day:
            return True

    return False


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Wire mapping
# --------------------------------------------------------------------------- #
def _summary(receipt: Receipt, payment: PaymentView | None) -> ReceiptSummary:
    if payment is None:
        # The receipt exists but its payment could not be resolved; the lookup
        # raises rather than returning None in production, so this is defensive.
        raise APIError(
            503,
            ErrorCode.PAYMENT_UNAVAILABLE,
            "Payment records are unavailable right now. Try again shortly.",
        )
    return ReceiptSummary(
        receipt_id=receipt.id,
        payment_id=receipt.payment_id,
        reference=_reference(receipt, payment),
        payee=payment.payee,
        amount=payment.amount,
        currency=payment.currency,
        kind=receipt.kind,
        # The status pill shows the receipt's verification state (screens/06).
        status=receipt.verification_status,
        issued_at=to_rfc3339(receipt.issued_at) if receipt.issued_at else None,
    )


def _reference(receipt: Receipt, payment: PaymentView) -> str:
    """The reference a user searches and quotes.

    The rail's reference when it has answered, then the official receipt number,
    then the payment id; all are real identifiers, so nothing here is invented
    (FEAT-008: never fabricate a reference).
    """
    for value in (payment.reference, receipt.receipt_number, payment.payment_id):
        if value:
            return value
    return payment.payment_id


def _receipt_out(receipt: Receipt) -> ReceiptOut:
    return ReceiptOut(
        id=receipt.id,
        payment_id=receipt.payment_id,
        user_id=receipt.user_id,
        kind=receipt.kind,
        receipt_number=receipt.receipt_number,
        verification_status=receipt.verification_status,
        document_ref=receipt.document_ref,
        issued_at=to_rfc3339(receipt.issued_at) if receipt.issued_at else None,
        created_at=to_rfc3339(receipt.created_at),
    )


def _payment_summary(payment: PaymentView) -> PaymentSummary:
    return PaymentSummary(
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


# --------------------------------------------------------------------------- #
# Cursor
# --------------------------------------------------------------------------- #
def _encode_cursor(receipt: Receipt) -> str:
    raw = f"{to_rfc3339(receipt.created_at)}|{receipt.id}".encode()
    return _CURSOR_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    if not cursor.startswith(_CURSOR_PREFIX):
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That page cursor is not valid.")
    encoded = cursor[len(_CURSOR_PREFIX) :]
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        stamp, receipt_id = raw.split("|", 1)
        created_at = datetime.fromisoformat(stamp)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That page cursor is not valid.") from None
    if not receipt_id:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That page cursor is not valid.")
    return created_at, receipt_id


__all__ = [
    "AWAITING_DOCUMENT_REF",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "capture_receipt",
    "get_document",
    "get_receipt",
    "list_receipts",
]
