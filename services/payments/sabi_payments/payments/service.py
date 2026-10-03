"""Payment authorisation, execution, listing, and refunding (FEAT-005, FEAT-009).

Rules the module owns:

- No payment without an explicit mandate binding the user, amount, and payee;
  the amount or payee changing after authorisation invalidates it (NFR-027).
- An amount above the user's set limit needs a second confirmation (FEAT-005).
- A duplicate authorisation or execution runs once and returns the same result
  (FEAT-005, "Duplicate authorisation").
- An unknown rail outcome is held ``pending`` and reconciled, never retried
  blindly; a refusal fails cleanly with no partial debit (architecture.md).
- Only a settled payment can be reversed or refunded, and a second refund for
  the same reference is blocked at the rail boundary rather than paid twice
  (FEAT-009; operations.md, "Duplicate-refund prevention").

The service is pure with respect to HTTP: it takes values, not requests, so the
same calls serve the HTTP surface and an in-process port.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sabi_payments.core.config import PaymentSettings
from sabi_payments.core.errors import PaymentError
from sabi_payments.core.ids import new_id
from sabi_payments.core.mandate import MandateRecord, MandateSigner, verify_mandate
from sabi_payments.core.rail import RailCharge, RailOutcome
from sabi_payments.core.state import PaymentState
from sabi_payments.db.audit import PaymentAuditLog
from sabi_payments.db.models import Payment, PaymentMandate
from sabi_payments.payments import repository
from sabi_payments.rail.disabled import DisabledRefundRail
from sabi_payments.rail.port import RailRefund, RailRefundOutcome, RefundRailPort

_CURRENCY = "NGN"
_TERMINAL_REFUND_STATES = frozenset({"reversed", "refunded"})


@dataclass(frozen=True, slots=True)
class AuthorisedPayment:
    payment_id: str
    status: str
    mandate_id: str
    rail_reference: str | None


@dataclass(frozen=True, slots=True)
class ExecutedPayment:
    payment_id: str
    status: str
    rail_reference: str | None


@dataclass(frozen=True, slots=True)
class RefundedPayment:
    payment_id: str
    status: str
    refund_reference: str | None


@dataclass(frozen=True, slots=True)
class PaymentPage:
    payments: list[Payment]
    next_cursor: str | None


def encode_cursor(payment: Payment) -> str:
    # Stored timestamps are UTC; SQLite drops tzinfo, so encode the naive UTC
    # value and decode it the same way to keep cursor comparison consistent.
    stamp = _as_utc_naive(payment.created_at).isoformat()
    raw = f"{stamp}|{payment.id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        stamp, identifier = raw.split("|", 1)
        return _as_utc_naive(datetime.fromisoformat(stamp)), identifier
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None


def _as_utc_naive(value: datetime) -> datetime:
    """Normalise to naive UTC so SQLite and Postgres compare identically."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class PaymentService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        settings: PaymentSettings,
        rail: RefundRailPort | None = None,
        audit: PaymentAuditLog | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._rail = rail or DisabledRefundRail()
        self._audit = audit or PaymentAuditLog(session_factory)
        self._signer = MandateSigner(settings.mandate_signing_key.get_secret_value())

    # --- C-017 ---------------------------------------------------------------

    def authorise(
        self,
        *,
        user_id: str,
        service_id: str,
        amount: int,
        currency: str,
        payee: str,
        payee_reference: str | None,
        payment_method_id: str | None,
        channel: str,
        second_confirmation: bool,
        idempotency_key: str | None,
        authorisation_limit: int | None = None,
        service_type: str = "bill",
    ) -> AuthorisedPayment:
        if amount <= 0:
            raise PaymentError(400, "invalid_request", "Enter an amount to pay.")
        if currency != _CURRENCY:
            raise PaymentError(400, "invalid_request", "Payments are settled in Naira.")
        if not payee.strip():
            raise PaymentError(400, "invalid_request", "This service has no collecting body.")

        limit = (
            authorisation_limit
            if authorisation_limit is not None
            else self._settings.default_authorisation_limit
        )
        if amount > limit and not second_confirmation:
            raise PaymentError(
                422,
                "validation_failed",
                "This amount is above your set limit. Confirm the payment to continue.",
            )

        with self._session_factory() as session:
            if payment_method_id is not None:
                method = repository.get_owned_method(session, payment_method_id, user_id)
                if method is None or method.status != "active":
                    raise PaymentError(
                        400, "invalid_request", "That payment method is not available."
                    )

            if idempotency_key:
                existing = repository.find_by_authorise_key(session, idempotency_key)
                if existing is not None:
                    raise PaymentError(
                        409,
                        "conflict",
                        "This authorisation was already received.",
                        {
                            "paymentId": existing.id,
                            "railReference": existing.rail_reference,
                        },
                    )

            now = datetime.now(UTC)
            mandate_id = new_id()
            nonce = new_id()
            # Whole-second expiry: the signed value must round-trip through the
            # store unchanged, and a sub-second mandate deadline buys nothing.
            expires_at = (now + timedelta(seconds=self._settings.mandate_ttl_seconds)).replace(
                microsecond=0
            )
            signature = self._signer.sign(
                user_id=user_id,
                amount=amount,
                currency=currency,
                payee=payee,
                payee_reference=payee_reference,
                nonce=nonce,
                expires_at=expires_at,
            )
            mandate = PaymentMandate(
                id=mandate_id,
                user_id=user_id,
                capability_id=None,
                amount=amount,
                currency=currency,
                payee=payee,
                payee_reference=payee_reference,
                nonce=nonce,
                signature=signature,
                status="issued",
                expires_at=expires_at,
            )
            payment = Payment(
                id=new_id(),
                user_id=user_id,
                service_id=service_id,
                mandate_id=mandate_id,
                payment_method_id=payment_method_id,
                type=service_type if service_type in {"government", "bill"} else "bill",
                amount=amount,
                currency=currency,
                payee=payee,
                channel=channel,
                status="authorized",
                idempotency_key=idempotency_key or new_id(),
            )
            session.add(mandate)
            session.add(payment)
            repository.add_event(
                session,
                payment_id=payment.id,
                status="authorized",
                actor="user",
                detail="authorisation received",
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise PaymentError(
                    409, "conflict", "This authorisation was already received."
                ) from None

        self._audit.append(
            "payment.authorized",
            actor_id=user_id,
            target=payment.id,
            detail={"amount": amount, "currency": currency, "channel": channel},
        )
        return AuthorisedPayment(
            payment_id=payment.id,
            status=payment.status,
            mandate_id=mandate_id,
            rail_reference=None,
        )

    # --- C-018 ---------------------------------------------------------------

    def execute(
        self,
        *,
        user_id: str,
        payment_id: str,
        mandate_id: str,
        idempotency_key: str,
    ) -> ExecutedPayment:
        if not idempotency_key:
            raise PaymentError(400, "invalid_request", "An idempotency key is required.")

        with self._session_factory() as session:
            payment = repository.get_owned_payment(session, payment_id, user_id)
            if payment is None:
                raise PaymentError(404, "not_found", "We could not find that payment.")

            # A replay of the same execution returns the stored result, not a
            # second debit (FEAT-005, "Duplicate authorisation").
            if payment.status in _EXECUTED_STATES and payment.idempotency_key == idempotency_key:
                return ExecutedPayment(payment.id, payment.status, payment.rail_reference)

            duplicate = repository.find_by_execute_key(session, idempotency_key)
            if duplicate is not None and duplicate.id != payment.id:
                raise PaymentError(409, "conflict", "That payment was already submitted.")

            mandate = repository.get_mandate(session, mandate_id)
            if mandate is None or mandate.user_id != user_id:
                raise PaymentError(
                    422, "validation_failed", "That mandate does not match this payment."
                )
            if mandate.status == "consumed" or payment.mandate_id != mandate_id:
                raise PaymentError(409, "conflict", "That authorisation was already used.")
            if _as_utc(mandate.expires_at) <= datetime.now(UTC):
                raise PaymentError(410, "challenge_expired", "That authorisation has expired.")

            record = _to_record(mandate)
            if not verify_mandate(
                record,
                user_id=user_id,
                amount=payment.amount,
                currency=payment.currency,
                payee=payment.payee,
            ) or not self._signer.verify_signature(record):
                raise PaymentError(
                    422,
                    "validation_failed",
                    "The amount or payee changed after you authorised it.",
                )

            outcome = self._rail.charge(
                RailCharge(
                    payment_id=payment.id,
                    user_id=user_id,
                    amount=payment.amount,
                    currency=payment.currency,
                    payee=payment.payee,
                    payee_reference=mandate.payee_reference,
                    payment_method_id=payment.payment_method_id,
                    idempotency_key=idempotency_key,
                )
            )
            _apply_outcome(payment, outcome)
            mandate.status = "consumed"
            payment.idempotency_key = idempotency_key
            repository.add_event(
                session,
                payment_id=payment.id,
                status=payment.status,
                actor="rail",
                detail=outcome.failure_reason,
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise PaymentError(409, "conflict", "That payment was already submitted.") from None

        self._audit.append(
            "payment.executed",
            actor_id=user_id,
            target=payment.id,
            detail={"status": payment.status, "railReference": payment.rail_reference},
        )
        if outcome.status == "failed" and _is_funding_refusal(outcome.failure_reason):
            raise PaymentError(
                402,
                "payment_required",
                outcome.failure_reason or "The payment could not be funded.",
            )
        return ExecutedPayment(payment.id, payment.status, payment.rail_reference)

    # --- C-019 ---------------------------------------------------------------

    def list_payments(
        self,
        *,
        user_id: str,
        cursor: str | None,
        limit: int,
        status: str | None,
    ) -> PaymentPage:
        resolved = decode_cursor(cursor) if cursor else None
        if cursor and resolved is None:
            raise PaymentError(400, "invalid_request", "That page cursor is not valid.")
        cursor_time, cursor_id = resolved if resolved else (None, None)

        with self._session_factory() as session:
            rows = repository.list_for_user(
                session,
                user_id=user_id,
                status=status,
                cursor_created_at=cursor_time,
                cursor_id=cursor_id,
                limit=limit,
            )
        page = rows[:limit]
        next_cursor = encode_cursor(page[-1]) if len(rows) > limit and page else None
        return PaymentPage(payments=page, next_cursor=next_cursor)

    # --- C-029 ---------------------------------------------------------------

    def refund(
        self,
        *,
        user_id: str,
        payment_id: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundedPayment:
        if not idempotency_key.strip():
            raise PaymentError(400, "invalid_request", "A refund needs an Idempotency-Key header.")

        with self._session_factory() as session:
            payment = repository.get_owned_payment(session, payment_id, user_id)
            if payment is None:
                # An unknown payment and another account's payment are the same
                # None, so the endpoint does not reveal which ids exist.
                raise PaymentError(404, "not_found", "We could not find that payment.")

            # A payment that already reversed or refunded has had its refund; a
            # second request is the duplicate FEAT-009 blocks by reference
            # (operations.md, "Duplicate-refund prevention").
            if payment.status in _TERMINAL_REFUND_STATES:
                raise _duplicate_refund()
            if payment.status != PaymentState.SUCCEEDED.value:
                raise PaymentError(
                    422,
                    "validation_failed",
                    "This payment cannot be refunded in its current state.",
                )

            outcome = self._rail.refund(
                RailRefund(
                    payment_id=payment.id,
                    user_id=user_id,
                    amount=payment.amount,
                    currency=payment.currency,
                    reference=payment.rail_reference,
                    reason=reason,
                    idempotency_key=idempotency_key,
                )
            )
            if outcome.status == "duplicate":
                raise _duplicate_refund()
            if outcome.status not in _TERMINAL_REFUND_STATES:
                # The rail did not settle the refund; the payment stays as it
                # was rather than being reported as reversed or refunded.
                raise PaymentError(
                    503,
                    "payment_unavailable",
                    "The refund could not be completed right now. Try again shortly.",
                )

            _apply_refund_outcome(payment, outcome)
            # ``reason`` is the user's own words; it belongs on the payment's
            # timeline and is not sent to application logs.
            repository.add_event(
                session,
                payment_id=payment.id,
                status=payment.status,
                actor="rail",
                detail=reason,
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise _duplicate_refund() from None

        self._audit.append(
            f"payment.{payment.status}",
            actor_id=user_id,
            target=payment.id,
            detail={"status": payment.status, "refundReference": outcome.refund_reference},
        )
        return RefundedPayment(payment.id, payment.status, outcome.refund_reference)


_EXECUTED_STATES = frozenset({"succeeded", "pending", "failed", "reversed", "refunded"})


def _to_record(mandate: PaymentMandate) -> MandateRecord:
    return MandateRecord(
        id=mandate.id,
        user_id=mandate.user_id,
        amount=mandate.amount,
        currency=mandate.currency,
        payee=mandate.payee,
        payee_reference=mandate.payee_reference,
        nonce=mandate.nonce,
        signature=mandate.signature,
        status=mandate.status,
        expires_at=_as_utc(mandate.expires_at),
    )


def _as_utc(value: datetime) -> datetime:
    """Treat a naive stored timestamp as UTC (SQLite drops tzinfo)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _apply_outcome(payment: Payment, outcome: RailOutcome) -> None:
    """Map a rail answer onto the payment, holding unknown outcomes pending."""
    payment.rail_reference = outcome.reference
    if outcome.status == "succeeded":
        payment.status = "succeeded"
        payment.completed_at = datetime.now(UTC)
        payment.failure_reason = None
    elif outcome.status == "failed":
        payment.status = "failed"
        payment.failure_reason = outcome.failure_reason or "The payment was declined."
    else:
        # Unknown outcome: hold pending for reconciliation, never a blind retry.
        payment.status = "pending"
        payment.failure_reason = outcome.failure_reason


def _is_funding_refusal(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return "insufficient" in lowered or "limit" in lowered


def _apply_refund_outcome(payment: Payment, outcome: RailRefundOutcome) -> None:
    """Move a settled payment to its terminal reversal or refund state.

    Only called for a settled outcome: an unknown one must not be written as a
    completed refund (FEAT-009).
    """
    payment.status = outcome.status


def _duplicate_refund() -> PaymentError:
    return PaymentError(409, "conflict", "A refund for this payment has already been requested.")


__all__ = [
    "AuthorisedPayment",
    "ExecutedPayment",
    "PaymentPage",
    "PaymentService",
    "RefundedPayment",
    "decode_cursor",
    "encode_cursor",
]
