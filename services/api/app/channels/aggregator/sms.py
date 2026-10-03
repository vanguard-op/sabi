"""Aggregator-backed SMS delivery for the channel gateway (FEAT-010, C-038).

The gateway declares an ``SmsDeliveryPort`` boundary; this module is one
implementation of it that talks to the mobile-network/USSD/SMS aggregator. It
does two jobs:

- ``send`` posts a reference or token to the aggregator through
  :mod:`app.channels.aggregator.client` and retains the message so its status
  can be read back.
- ``status`` answers C-038, scoped to the subscriber: a message for another
  number resolves to ``None`` exactly as an unknown reference does, so the
  existence of another subscriber's message is never inferable (the gateway
  turns both into a 404).

When the aggregator later posts a delivery report, :meth:`record_report` folds
it into the retained message's status. A failed send still retains the message
as queued — the notification service's retry is the contract's promise that a
reference is delayed, never lost (FEAT-010, alternate path C).

The ledger is process-local. A multi-worker deployment substitutes a shared
store, or lets the notification service own delivery and keeps this port as a
thin caller; the gateway contract does not change either way. An MSISDN is held
only to scope a lookup and is never logged.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from app.channels.aggregator.callback import SmsDeliveryReport
from app.channels.aggregator.client import AggregatorClient
from app.channels.ports import SmsMessage
from app.core.time import utcnow


class AggregatorSmsDeliveryPort:
    """Deliver SMS through the aggregator and report status by reference."""

    def __init__(
        self,
        *,
        client: AggregatorClient | None = None,
        messages: Iterable[SmsMessage] = (),
    ) -> None:
        self._client = client
        self._by_ref: dict[str, SmsMessage] = {message.reference: message for message in messages}
        # Delivery reports can arrive before the send is retained (an aggregator
        # may report fast). Hold them so a late ``send`` can settle from the
        # report rather than sit at queued.
        self._reports: dict[str, SmsDeliveryReport] = {}

    @property
    def client(self) -> AggregatorClient | None:
        """The transport, for the deployment to close at shutdown."""

        return self._client

    def send(self, *, message: SmsMessage) -> None:
        retained = (
            message if message.created_at is not None else replace(message, created_at=utcnow())
        )
        # Settle from an early delivery report so a fast aggregator is reflected.
        report = self._reports.pop(retained.reference, None)
        if report is not None:
            retained = replace(retained, status=report.status)
        self._by_ref[retained.reference] = retained

        if self._client is None:
            # No transport wired: retain the message as queued so C-038 still
            # answers and the notification path can retry. This mirrors the
            # gateway's "retain for retry, never lose the reference" behaviour.
            return
        # A send failure raises from the client; the gateway already treats that
        # as a retained-for-retry condition and does not fail the payment. The
        # message stays queued here so its status is readable meanwhile.
        self._client.send_sms(msisdn=retained.msisdn, body=retained.body)

    def status(self, *, msisdn: str, reference: str) -> SmsMessage | None:
        message = self._by_ref.get(reference)
        if message is None or message.msisdn != msisdn:
            return None
        return message

    def record_report(self, report: SmsDeliveryReport) -> None:
        """Fold an inbound delivery report into the retained message's status.

        A report for a reference this port does not hold is remembered, so a
        report that races ahead of its send still settles the message.
        """

        message = self._by_ref.get(report.reference)
        if message is None:
            self._reports[report.reference] = report
            return
        if message.msisdn != report.msisdn:
            # A report for another subscriber's message does not mutate this
            # one; the mismatch is dropped rather than trusted.
            return
        self._by_ref[report.reference] = replace(message, status=report.status)


__all__ = ["AggregatorSmsDeliveryPort"]
