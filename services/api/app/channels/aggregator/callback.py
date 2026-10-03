"""Inbound translation between the USSD/SMS aggregator and the channel gateway.

The aggregator drives a USSD session by calling Sabi's callback URL once per
keypad entry. Africa's Talking, the dominant format and the one the reference
aggregators document, posts ``application/x-www-form-urlencoded`` fields:

- ``sessionId``: the aggregator's session identifier, stable across the session;
- ``phoneNumber``: the subscriber's MSISDN — the channel identity, and the
  reason no ``X-Channel-Msisdn`` header exists on the wire;
- ``serviceCode``: the short code the user dialled;
- ``text``: the inputs so far, ``*``-joined; empty on the first call (the
  subscriber has only dialled).

The gateway's C-036 request wants the latest input and the step it answers, not
the cumulative ``text``, so this module takes the last ``*``-separated segment.
The gateway's answer is a plain prompt; the aggregator wants that prompt
prefixed with ``CON`` to continue or ``END`` to close, so this module renders
the prefix from the ``done`` flag.

Some aggregators post JSON instead of form fields and use ``msisdn`` for the
number. :func:`parse_ussd_callback` accepts either shape so the same gateway
sits behind a form-posting or a JSON-posting aggregator without code changes.

SMS delivery reports arrive as a separate callback carrying the aggregator's
message id, a status word, and the recipient's number; :func:`parse_delivery_report`
normalises them for :mod:`app.channels.aggregator.sms`.

An MSISDN is personal data: the parsed value is returned to the caller and never
logged here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.channels import schemas as channel_schemas

# Response prefixes the aggregator requires: continue the session or end it.
CONTINUE_PREFIX = "CON"
END_PREFIX = "END"

# Field names seen on the wire. The form format (Africa's Talking) uses
# ``phoneNumber``/``text``; a JSON aggregator commonly uses
# ``msisdn``/``input``/``text`` with the same meaning.
_MSISDN_KEYS = ("phoneNumber", "msisdn", "MSISDN", "phone_number")
_SESSION_KEYS = ("sessionId", "session_id")
_TEXT_KEYS = ("text", "input")
_SERVICE_CODE_KEYS = ("serviceCode", "service_code", "code")

# Delivery-report fields. ``id`` is the aggregator's message id; ``status`` is a
# vendor-specific word such as ``Success``/``Failed``; ``phoneNumber`` is the
# recipient. A failure reason is carried for the C-038 status view.
_REPORT_ID_KEYS = ("id", "messageId", "message_id", "reference")
_REPORT_STATUS_KEYS = ("status", "deliveryStatus", "delivery_status")
_REPORT_MSISDN_KEYS = _MSISDN_KEYS
_REPORT_REASON_KEYS = ("failureReason", "failure_reason", "reason")


@dataclass(frozen=True, slots=True)
class UssdCallback:
    """One inbound USSD callback, normalised to the gateway's vocabulary.

    ``input_value`` is the latest keypad entry, or ``None`` when the subscriber
    has only dialled and the gateway should open the session. ``step`` is not on
    the aggregator wire — the gateway infers it from the session — so it is
    always ``None`` on a parsed callback.
    """

    session_id: str
    msisdn: str
    input_value: str | None
    service_code: str | None = None
    step: str | None = None

    def to_session_request(self) -> channel_schemas.UssdSessionRequest:
        """Build the C-036 request the gateway serves."""

        return channel_schemas.UssdSessionRequest(
            sessionId=self.session_id,
            msisdn=self.msisdn,
            input=self.input_value,
            step=self.step,
        )


@dataclass(frozen=True, slots=True)
class SmsDeliveryReport:
    """One inbound SMS delivery report, normalised for the SMS ledger."""

    reference: str
    msisdn: str
    status: str
    reason: str | None = None


class CallbackPayloadError(ValueError):
    """An inbound callback is missing a field the gateway cannot work without.

    It is a caller error, not an APIError: this runs at the channel boundary
    before the gateway is reached, and the aggregator expects a plain 4xx, not
    the JSON error envelope the mobile client sees. The message names the
    missing field only, never a submitted value.
    """


def _first(payload: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _required(payload: Mapping[str, object], keys: tuple[str, ...], field: str) -> str:
    value = _first(payload, keys)
    if value is None:
        raise CallbackPayloadError(f"{field} is required")
    return value


def parse_ussd_callback(payload: Mapping[str, object]) -> UssdCallback:
    """Read one inbound USSD callback from a form or JSON mapping.

    Only the fields the gateway needs are read. The subscriber's number and the
    aggregator session id are mandatory; ``text`` is optional and empty on the
    first call. A cumulative ``text`` of ``1*2*3`` becomes the single input
    ``3``; an empty ``text`` becomes ``None`` so the gateway opens the session.
    """

    session_id = _required(payload, _SESSION_KEYS, "sessionId")
    msisdn = _required(payload, _MSISDN_KEYS, "phoneNumber")

    raw_text = _first(payload, _TEXT_KEYS)
    input_value: str | None = None
    if raw_text is not None:
        # The aggregator sends the whole keypad path; the gateway wants the one
        # answer that produced this call, which is the final segment.
        segment = raw_text.rsplit("*", 1)[-1].strip()
        input_value = segment or None

    service_code = _first(payload, _SERVICE_CODE_KEYS)
    return UssdCallback(
        session_id=session_id,
        msisdn=msisdn,
        input_value=input_value,
        service_code=service_code,
    )


def render_ussd_response(*, prompt: str, done: bool) -> str:
    """Render the gateway's answer as the aggregator's ``CON``/``END`` text.

    ``done`` closes the session with ``END``; otherwise the prompt is continued
    with ``CON``. A malformed response (no prefix) makes the aggregator drop the
    session, so the prefix is always present even for an empty prompt.
    """

    prefix = END_PREFIX if done else CONTINUE_PREFIX
    body = prompt.strip()
    return f"{prefix} {body}" if body else prefix


def parse_delivery_report(payload: Mapping[str, object]) -> SmsDeliveryReport:
    """Read one inbound SMS delivery report from a form or JSON mapping."""

    reference = _required(payload, _REPORT_ID_KEYS, "id")
    msisdn = _required(payload, _REPORT_MSISDN_KEYS, "phoneNumber")
    status = _first(payload, _REPORT_STATUS_KEYS) or "queued"
    reason = _first(payload, _REPORT_REASON_KEYS)
    return SmsDeliveryReport(
        reference=reference,
        msisdn=msisdn,
        status=_normalise_status(status),
        reason=reason,
    )


def _normalise_status(status: str) -> str:
    """Map a vendor status word onto the delivery states C-038 reports.

    Africa's Talking sends ``Success`` for a delivered message and a
    ``failureReason`` alongside a failure; other aggregators use
    ``Sent``/``Delivered``/``Queued``/``Failed`` directly. Anything unrecognised
    is held as ``queued`` so an unknown word never reports a false delivery.
    """

    lowered = status.strip().lower()
    if lowered in {"success", "delivered"}:
        return "delivered"
    if lowered in {"sent", "accepted"}:
        return "sent"
    if lowered in {"failed", "rejected", "undelivered"}:
        return "failed"
    return "queued"


__all__ = [
    "CONTINUE_PREFIX",
    "END_PREFIX",
    "CallbackPayloadError",
    "SmsDeliveryReport",
    "UssdCallback",
    "parse_delivery_report",
    "parse_ussd_callback",
    "render_ussd_response",
]
