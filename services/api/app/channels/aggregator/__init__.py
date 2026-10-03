"""Aggregator adapter for the USSD/SMS channel gateway (FEAT-010, C-036 to C-038).

The gateway in :mod:`app.channels` speaks one channel-neutral conversation:
C-036 carries ``sessionId``/``msisdn``/``input``/``step`` as JSON and answers
with ``prompt``/``step``/``done``. The mobile-network/USSD/SMS aggregator
(architecture.md, "External integrations") speaks a different wire format. This
package is the translation layer between the two; it owns no contract of its own
and never reimplements the conversation.

Two directions:

- **Inbound.** The aggregator calls Sabi's callback URL with the subscriber's
  number and the digit they pressed. :mod:`callback` reads that payload into the
  fields C-036 expects and renders the gateway's answer back into the
  aggregator's ``CON``/``END`` response; the same module reads SMS delivery
  reports.
- **Outbound.** :mod:`sms` implements the gateway's ``SmsDeliveryPort`` over the
  aggregator's send API, retaining each message so C-038 can report its status;
  :mod:`client` is the HTTP boundary the port talks to.

The subscriber's MSISDN is personal data (NFR-040): it is read from the inbound
payload, passed to the gateway to bind the session, and never logged or echoed.
"""
