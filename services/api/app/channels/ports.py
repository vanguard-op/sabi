"""Boundaries from the channel gateway to identity, payments, and SMS delivery.

The gateway owns the USSD conversation; three capabilities live outside it and
are bound on ``app.state`` by the deployment:

- ``app.state.channels_identity``: a ``ChannelIdentityLookup`` that resolves an
  MSISDN to the account it is linked to. Channel links live in the identity
  module (C-007); the gateway never creates a second account (FEAT-001).
- ``app.state.channels_payments``: a ``ChannelPaymentPort`` that authorises and
  executes a payment through the isolated payment module. The gateway never
  touches the payment store directly (architecture.md, "Payment Module").
- ``app.state.channels_sms``: an ``SmsDeliveryPort`` for the notification
  service to deliver a reference or token and report its status (FEAT-010).

Every default refuses with a system error rather than inventing an account, a
payment, or a delivery, matching the port pattern used by the case and receipt
modules. The in-memory implementations are for development and tests only.

Identity is personal data: an MSISDN is never logged or echoed back in a prompt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from fastapi import Request

from app.core.errors import APIError, ErrorCode

# A channel capability that is present but whose backing dependency is absent is
# a system condition, reported like the payment store boundary does.
CHANNEL_UNAVAILABLE = "channel_unavailable"


@dataclass(frozen=True, slots=True)
class ChannelIdentity:
    """The account a channel address is linked to."""

    user_id: str
    locale: str


@dataclass(frozen=True, slots=True)
class PaymentOutcome:
    """The payment module's answer to a USSD authorisation.

    ``status`` is ``succeeded``, ``pending``, or ``failed``; ``reference`` is the
    rail reference when one exists. A pending outcome means the session may time
    out with the payment still to resolve (FEAT-010, alternate path B).
    """

    status: str
    reference: str | None = None
    payment_id: str | None = None


@dataclass(frozen=True, slots=True)
class SmsMessage:
    """An SMS handed to the notification service for delivery."""

    reference: str
    msisdn: str
    body: str
    status: str = "queued"
    token: str | None = None
    created_at: datetime | None = None


class ChannelIdentityLookup(Protocol):
    """Resolve a channel address to its linked account, if any."""

    def resolve(self, *, msisdn: str) -> ChannelIdentity | None:
        """Return the linked account, or None when the number is not linked."""


class ChannelPaymentPort(Protocol):
    """Authorise and execute a payment from a channel session, keyed for idempotency."""

    def authorise(
        self,
        *,
        user_id: str,
        msisdn: str,
        session_id: str,
        idempotency_key: str,
        service_id: str,
        recipient: str,
        amount: int,
        currency: str,
    ) -> PaymentOutcome: ...

    def pending_for(self, *, user_id: str, msisdn: str) -> PaymentOutcome | None:
        """Return a payment still pending for the account and channel, if any.

        A timed-out USSD session resumes this payment rather than starting a new
        one (FEAT-010, alternate path B).
        """


class SmsDeliveryPort(Protocol):
    """Queue an SMS and report its delivery status by reference."""

    def send(self, *, message: SmsMessage) -> None: ...

    def status(self, *, msisdn: str, reference: str) -> SmsMessage | None:
        """Return the message if it exists and belongs to ``msisdn``."""


class UnavailableChannelIdentityLookup:
    """Default identity boundary when the identity module is not wired."""

    def resolve(self, *, msisdn: str) -> ChannelIdentity | None:
        raise _unavailable()


class UnavailableChannelPaymentPort:
    """Default payment boundary when the isolated payment module is not wired."""

    def authorise(
        self,
        *,
        user_id: str,
        msisdn: str,
        session_id: str,
        idempotency_key: str,
        service_id: str,
        recipient: str,
        amount: int,
        currency: str,
    ) -> PaymentOutcome:
        raise _unavailable()

    def pending_for(self, *, user_id: str, msisdn: str) -> PaymentOutcome | None:
        raise _unavailable()


class UnavailableSmsDeliveryPort:
    """Default SMS boundary when the notification service is not wired."""

    def send(self, *, message: SmsMessage) -> None:
        raise _unavailable()

    def status(self, *, msisdn: str, reference: str) -> SmsMessage | None:
        raise _unavailable()


class InMemoryChannelIdentityLookup:
    """Process-local channel-link lookup for development and tests."""

    def __init__(self, links: dict[str, ChannelIdentity] | None = None) -> None:
        self._by_msisdn = dict(links or {})

    def link(self, msisdn: str, *, user_id: str, locale: str = "en") -> None:
        self._by_msisdn[msisdn] = ChannelIdentity(user_id=user_id, locale=locale)

    def resolve(self, *, msisdn: str) -> ChannelIdentity | None:
        return self._by_msisdn.get(msisdn)


class InMemoryChannelPaymentPort:
    """Fake payment module for development and tests.

    It records authorisation calls and returns a configured outcome; a repeated
    idempotency key returns the first outcome, so a duplicate is executed once.
    """

    def __init__(self, outcome: PaymentOutcome | None = None) -> None:
        self._outcome = outcome or PaymentOutcome(status="succeeded", reference="rail-1")
        self.calls: list[dict[str, str | int]] = []
        self._by_key: dict[str, PaymentOutcome] = {}
        self._pending: dict[tuple[str, str], PaymentOutcome] = {}

    def set_pending(self, *, user_id: str, msisdn: str, outcome: PaymentOutcome | None) -> None:
        """Record (or clear) a pending payment for the account and channel."""
        key = (user_id, msisdn)
        if outcome is None:
            self._pending.pop(key, None)
        else:
            self._pending[key] = outcome

    def pending_for(self, *, user_id: str, msisdn: str) -> PaymentOutcome | None:
        return self._pending.get((user_id, msisdn))

    def authorise(
        self,
        *,
        user_id: str,
        msisdn: str,
        session_id: str,
        idempotency_key: str,
        service_id: str,
        recipient: str,
        amount: int,
        currency: str,
    ) -> PaymentOutcome:
        self.calls.append(
            {
                "user_id": user_id,
                "msisdn": msisdn,
                "session_id": session_id,
                "idempotency_key": idempotency_key,
                "service_id": service_id,
                "recipient": recipient,
                "amount": amount,
                "currency": currency,
            }
        )
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        self._by_key[idempotency_key] = self._outcome
        return self._outcome


class InMemorySmsDeliveryPort:
    """Process-local SMS delivery ledger for development and tests."""

    def __init__(self, messages: Sequence[SmsMessage] = ()) -> None:
        self._by_ref: dict[str, SmsMessage] = {message.reference: message for message in messages}

    def send(self, *, message: SmsMessage) -> None:
        self._by_ref[message.reference] = message

    def status(self, *, msisdn: str, reference: str) -> SmsMessage | None:
        message = self._by_ref.get(reference)
        if message is None or message.msisdn != msisdn:
            return None
        return message


def _unavailable() -> APIError:
    return APIError(
        503,
        CHANNEL_UNAVAILABLE,
        "The channel service is unavailable right now. Try again shortly.",
    )


def get_channel_identity(request: Request) -> ChannelIdentityLookup:
    lookup = getattr(request.app.state, "channels_identity", None)
    if lookup is None:
        return UnavailableChannelIdentityLookup()
    return lookup


def get_channel_payments(request: Request) -> ChannelPaymentPort:
    port = getattr(request.app.state, "channels_payments", None)
    if port is None:
        return UnavailableChannelPaymentPort()
    return port


def get_sms_delivery(request: Request) -> SmsDeliveryPort:
    port = getattr(request.app.state, "channels_sms", None)
    if port is None:
        return UnavailableSmsDeliveryPort()
    return port


__all__ = [
    "CHANNEL_UNAVAILABLE",
    "ChannelIdentity",
    "ChannelIdentityLookup",
    "ChannelPaymentPort",
    "InMemoryChannelIdentityLookup",
    "InMemoryChannelPaymentPort",
    "InMemorySmsDeliveryPort",
    "PaymentOutcome",
    "SmsDeliveryPort",
    "SmsMessage",
    "UnavailableChannelIdentityLookup",
    "UnavailableChannelPaymentPort",
    "UnavailableSmsDeliveryPort",
    "get_channel_identity",
    "get_channel_payments",
    "get_sms_delivery",
]
