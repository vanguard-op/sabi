"""Boundaries from the everyday-bill flows to the biller and the payment module.

A bill payment is resolved against a biller and settled through the isolated
payment module, both outside this package:

- ``app.state.bills_biller``: a ``BillerPort`` that validates a recipient and
  reports whether the biller can be reached. An unreachable biller prevents the
  payment (FEAT-007, user-flow Flow 3 alternate B).
- ``app.state.bills_payments``: a ``BillPaymentPort`` that authorises and
  executes a bill in one step through the isolated payment module. The gateway
  never touches the payment store directly (architecture.md, "Payment Module").
- ``app.state.bills_payment_lookup``: a ``PaymentLookup`` used to read a stored
  payment when a token is fetched (C-035).

The read and refund boundary shapes live once in :mod:`app.payments_port`; this
module re-exports them rather than redefining a payment view. Only the two
bill-specific writes above are declared here, beside their consumer, the same
way the channel gateway declares its own payment port. Every default refuses:
an unwired biller or payment module reports ``payment_unavailable`` rather than
inventing a validated recipient, a payment, or a token (FEAT-007).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

from app.core.errors import APIError, ErrorCode
from app.payments_port import (
    PaymentLookup,
    PaymentView,
    UnavailablePaymentLookup,
)

# A biller capability that is present but whose backing dependency is absent is
# a system condition, reported like the payment store boundary does.
BILLER_UNAVAILABLE = "biller_unavailable"

# The rail's refusal when the account cannot cover the bill (C-034, 402).
INSUFFICIENT_FUNDS = "insufficient_funds"


@dataclass(frozen=True, slots=True)
class BillAmountRange:
    """A variable bill's accepted amount band, in minor units (kobo)."""

    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class BillValidation:
    """The biller's answer to a recipient lookup (C-033).

    ``valid`` is false with a plain ``reason`` when the identifier is not a
    recognised account or the amount falls outside the biller's range. A
    ``known_amount`` is the biller-confirmed amount for a fixed or looked-up
    bill; ``range`` is present only for a variable bill (FEAT-007).
    """

    valid: bool
    known_amount: int | None = None
    currency: str = "NGN"
    amount_range: BillAmountRange | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BillPaymentResult:
    """The payment module's answer to one bill authorise-and-execute.

    ``status`` is the payment state after the rail answered (``succeeded``,
    ``pending``, or ``failed``). ``token`` is present for a token product such as
    prepaid electricity; ``reference`` is the rail's transaction reference;
    ``receipt_id`` is set when the flow captured a receipt. A pending payment is
    held open and its token retrieved on a later check (FEAT-007, user-flow
    Flow 3 alternate C).
    """

    payment_id: str
    status: str
    token: str | None = None
    reference: str | None = None
    receipt_id: str | None = None


class BillerPort(Protocol):
    """Validate a recipient and report whether the biller can be reached."""

    def health(self, *, service_id: str) -> str:
        """Return ``healthy``, ``degraded``, or ``unavailable`` for the biller."""

    def validate(
        self,
        *,
        service_id: str,
        recipient: str,
        amount: int | None,
    ) -> BillValidation:
        """Look the recipient up and confirm the amount when one is given."""

    def fetch_token(self, *, service_id: str, recipient: str, payment_id: str) -> str | None:
        """Return a product token the biller has issued, or ``None`` yet."""


class BillPaymentPort(Protocol):
    """Authorise and execute one bill through the isolated payment module.

    The call is keyed for idempotency: a repeated key returns the first result
    rather than debiting twice. A refusal surfaces as an ``APIError`` with the
    contract's status: 409 for a duplicate authorisation, 402 when the account
    cannot cover the amount, 503 when the biller is offline.
    """

    def pay(
        self,
        *,
        user_id: str,
        service_id: str,
        payee: str,
        recipient: str,
        amount: int,
        currency: str,
        channel: str,
        idempotency_key: str,
    ) -> BillPaymentResult: ...


class UnavailableBillerPort:
    """Default biller boundary when no biller integration is wired."""

    def health(self, *, service_id: str) -> str:
        return "unavailable"

    def validate(
        self,
        *,
        service_id: str,
        recipient: str,
        amount: int | None,
    ) -> BillValidation:
        raise _biller_unavailable()

    def fetch_token(self, *, service_id: str, recipient: str, payment_id: str) -> str | None:
        raise _biller_unavailable()


class UnavailableBillPaymentPort:
    """Default payment boundary when the isolated payment module is not wired."""

    def pay(
        self,
        *,
        user_id: str,
        service_id: str,
        payee: str,
        recipient: str,
        amount: int,
        currency: str,
        channel: str,
        idempotency_key: str,
    ) -> BillPaymentResult:
        raise APIError(
            503,
            ErrorCode.PAYMENT_UNAVAILABLE,
            "Payments are paused right now. Your request is safe; try again shortly.",
        )


class InMemoryBillerPort:
    """Process-local biller for development and tests.

    A recipient is valid when it is registered. ``offline`` makes the biller
    report ``unavailable`` so the pay endpoint can be exercised against a
    biller outage without a network.
    """

    def __init__(self, *, offline: bool = False) -> None:
        self._recipients: dict[tuple[str, str], BillValidation] = {}
        self._tokens: dict[str, str] = {}
        self._offline = offline

    def register(
        self,
        *,
        service_id: str,
        recipient: str,
        known_amount: int | None = None,
        amount_range: BillAmountRange | None = None,
        currency: str = "NGN",
    ) -> None:
        self._recipients[(service_id, recipient)] = BillValidation(
            valid=True,
            known_amount=known_amount,
            currency=currency,
            amount_range=amount_range,
        )

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    def issue_token(self, *, payment_id: str, token: str) -> None:
        self._tokens[payment_id] = token

    def health(self, *, service_id: str) -> str:
        return "unavailable" if self._offline else "healthy"

    def validate(
        self,
        *,
        service_id: str,
        recipient: str,
        amount: int | None,
    ) -> BillValidation:
        if self._offline:
            raise _biller_unavailable()
        found = self._recipients.get((service_id, recipient))
        if found is None:
            return BillValidation(valid=False, reason="That account was not found.")
        if amount is not None and found.amount_range is not None:
            if not found.amount_range.minimum <= amount <= found.amount_range.maximum:
                return BillValidation(
                    valid=False,
                    currency=found.currency,
                    amount_range=found.amount_range,
                    reason="The amount is outside the range this biller accepts.",
                )
        return found

    def fetch_token(self, *, service_id: str, recipient: str, payment_id: str) -> str | None:
        return self._tokens.get(payment_id)


class InMemoryBillPaymentPort:
    """Fake payment module for development and tests.

    It records each call and returns a configured result; a repeated idempotency
    key returns the first result, so a duplicate is executed once (FEAT-007,
    "Duplicate authorisation").
    """

    def __init__(self, result: BillPaymentResult | None = None) -> None:
        self._result = result or BillPaymentResult(
            payment_id="payment-1", status="succeeded", token="TOKEN-1"
        )
        self.calls: list[dict[str, str | int]] = []
        self._by_key: dict[str, BillPaymentResult] = {}
        self.duplicate_error: APIError | None = None
        self.failure_error: APIError | None = None

    def set_result(self, result: BillPaymentResult) -> None:
        self._result = result

    def pay(
        self,
        *,
        user_id: str,
        service_id: str,
        payee: str,
        recipient: str,
        amount: int,
        currency: str,
        channel: str,
        idempotency_key: str,
    ) -> BillPaymentResult:
        self.calls.append(
            {
                "user_id": user_id,
                "service_id": service_id,
                "payee": payee,
                "recipient": recipient,
                "amount": amount,
                "currency": currency,
                "channel": channel,
                "idempotency_key": idempotency_key,
            }
        )
        if self.failure_error is not None:
            raise self.failure_error
        if idempotency_key in self._by_key:
            if self.duplicate_error is not None:
                raise self.duplicate_error
            return self._by_key[idempotency_key]
        self._by_key[idempotency_key] = self._result
        return self._result


def get_biller(request: Request) -> BillerPort:
    port = getattr(request.app.state, "bills_biller", None)
    if port is None:
        return UnavailableBillerPort()
    return port


def get_payment_port(request: Request) -> BillPaymentPort:
    port = getattr(request.app.state, "bills_payments", None)
    if port is None:
        return UnavailableBillPaymentPort()
    return port


def get_payment_lookup(request: Request) -> PaymentLookup:
    lookup = getattr(request.app.state, "bills_payment_lookup", None)
    if lookup is None:
        return UnavailablePaymentLookup()
    return lookup


def _biller_unavailable() -> APIError:
    return APIError(
        503,
        BILLER_UNAVAILABLE,
        "This biller is offline right now. Your payment was not started; try again shortly.",
    )


__all__ = [
    "BILLER_UNAVAILABLE",
    "INSUFFICIENT_FUNDS",
    "BillAmountRange",
    "BillPaymentPort",
    "BillPaymentResult",
    "BillValidation",
    "BillerPort",
    "InMemoryBillPaymentPort",
    "InMemoryBillerPort",
    "PaymentLookup",
    "PaymentView",
    "UnavailableBillPaymentPort",
    "UnavailableBillerPort",
    "get_biller",
    "get_payment_lookup",
    "get_payment_port",
]
