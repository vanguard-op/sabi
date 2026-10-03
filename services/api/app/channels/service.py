"""USSD conversation policy and SMS status resolution (FEAT-010, C-036 to C-038).

The state machine lives here rather than in the router so the rules can be
tested without a running gateway. A session advances menu -> service -> details
-> confirm, after which C-037 authorises the payment. Session time is billed to
the user's airtime, so prompts are short and steps are few (NFR-006); the
configured cap is 120 seconds (architecture.md, "USSD/SMS Channel Gateway").

Two behaviours are policy, not plumbing:

- An unlinked number is told to link in the app and no payment can be
  authorised from it; the gateway never creates a second account (FEAT-001,
  user-flow, "Channel Identity Linking").
- A session that times out before authorisation executes nothing. One that times
  out after authorisation resumes the pending payment on the next dial rather
  than restarting it (FEAT-010, alternate path B).

Identity is personal data: an MSISDN is held only to bind a session and to scope
an SMS, and is never placed in a prompt or an error message.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.channels.ports import (
    ChannelIdentityLookup,
    ChannelPaymentPort,
    SmsDeliveryPort,
    SmsMessage,
)
from app.channels.schemas import (
    AFFIRMATIVE,
    PROMPTS,
    STEP_CONFIRM,
    STEP_DETAILS,
    STEP_MENU,
    STEP_RESULT,
    STEP_SERVICE,
)
from app.channels.sessions import (
    UssdSession,
    UssdSessionStore,
    is_expired,
    open_session,
    touch,
)
from app.core.errors import APIError, ErrorCode
from app.core.ids import new_id
from app.core.time import utcnow

# The two menu choices kept to the highest-frequency actions (FEAT-010).
MENU_PAY = "1"
MENU_CHECK = "2"

# Fallback locale when a stored preference is not one the prompts hold.
DEFAULT_LOCALE = "en"


def _prompt(key: str, locale: str) -> str:
    """Return a localised prompt, falling back to English with a note."""

    table = PROMPTS.get(key)
    if table is None:
        return PROMPTS["invalid"].get(DEFAULT_LOCALE, "")
    text = table.get(locale)
    if text is not None:
        return text
    return table.get(DEFAULT_LOCALE, "")


def _invalid_input() -> APIError:
    return APIError(400, ErrorCode.INVALID_REQUEST, "That session input is not valid.")


def _session_expired(*, resumable: bool) -> APIError:
    message = (
        "This session has timed out. The payment is still pending; dial again to continue."
        if resumable
        else "This session has timed out. Dial again to start a new one."
    )
    return APIError(
        410,
        "session_expired",
        message,
        {"resumable": resumable},
    )


def open_or_advance(
    *,
    store: UssdSessionStore,
    identity: ChannelIdentityLookup,
    payments: ChannelPaymentPort,
    session_id: str,
    msisdn: str,
    input_value: str | None,
    step: str | None,
    timeout_seconds: int,
    clock: Callable[[], datetime] = utcnow,
) -> dict[str, object]:
    """Drive one USSD step and return the next prompt, step, and done flag.

    A call with neither ``input`` nor ``step`` opens the session. A call carrying
    either continues an existing one.
    """

    existing = store.get(session_id)

    if existing is not None and existing.msisdn != msisdn:
        # The session id is bound to one subscriber; a different number driving
        # it is a conflict, not a new conversation (C-036, 409).
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "This session is open on another number. Dial again to start a new one.",
        )

    if existing is None:
        return _open(
            store=store,
            identity=identity,
            payments=payments,
            session_id=session_id,
            msisdn=msisdn,
            timeout_seconds=timeout_seconds,
            clock=clock,
        )

    if is_expired(existing, clock=clock):
        raise _session_expired(resumable=existing.authorised and existing.payment_pending)

    touch(existing, timeout_seconds=timeout_seconds, clock=clock)

    if existing.user_id == "":
        # An unlinked number stays unlinked; it cannot authorise a payment and
        # no account is created for it (FEAT-001).
        store.save(existing)
        return {
            "prompt": _prompt("unlinked", existing.locale),
            "step": existing.step,
            "done": True,
        }

    return _advance(
        store=store,
        session=existing,
        input_value=input_value,
        step=step,
    )


def _open(
    *,
    store: UssdSessionStore,
    identity: ChannelIdentityLookup,
    payments: ChannelPaymentPort,
    session_id: str,
    msisdn: str,
    timeout_seconds: int,
    clock: Callable[[], datetime],
) -> dict[str, object]:
    account = identity.resolve(msisdn=msisdn)
    if account is None:
        # Record an unlinked session so a retry with the same id is consistent,
        # but never mint an account for the number (FEAT-001).
        unlinked = open_session(
            session_id=session_id,
            msisdn=msisdn,
            user_id="",
            locale=DEFAULT_LOCALE,
            timeout_seconds=timeout_seconds,
            clock=clock,
        )
        unlinked.done = True
        store.save(unlinked)
        return {
            "prompt": _prompt("unlinked", unlinked.locale),
            "step": unlinked.step,
            "done": True,
        }

    session = open_session(
        session_id=session_id,
        msisdn=msisdn,
        user_id=account.user_id,
        locale=account.locale,
        timeout_seconds=timeout_seconds,
        clock=clock,
    )

    # A payment left pending by a previous, timed-out session resumes here rather
    # than being restarted (FEAT-010, alternate path B). The new session carries
    # the pending outcome and reports it at the result step.
    pending = payments.pending_for(user_id=account.user_id, msisdn=msisdn)
    if pending is not None and pending.status == "pending":
        session.payment_pending = True
        session.payment_status = pending.status
        session.payment_reference = pending.reference
        session.step = STEP_RESULT
        session.done = True
        store.save(session)
        return {
            "prompt": _prompt("timed_out_pending", session.locale),
            "step": STEP_RESULT,
            "done": True,
        }

    store.save(session)
    return {
        "prompt": _prompt(STEP_MENU, session.locale),
        "step": STEP_MENU,
        "done": False,
    }


def _advance(
    *,
    store: UssdSessionStore,
    session: UssdSession,
    input_value: str | None,
    step: str | None,
) -> dict[str, object]:
    # The gateway echoes the step it was answering; a mismatch means the call is
    # out of sequence, which is a bad input rather than a silent restart.
    if step is not None and step != session.step:
        raise _invalid_input()

    if input_value is None:
        # A continue with no input re-renders the current prompt.
        return {
            "prompt": _prompt(session.step, session.locale),
            "step": session.step,
            "done": session.done,
        }

    reply = input_value.strip()
    if not reply:
        raise _invalid_input()

    if session.step == STEP_MENU:
        return _menu(store=store, session=session, reply=reply)
    if session.step == STEP_SERVICE:
        return _service(store=store, session=session, reply=reply)
    if session.step == STEP_DETAILS:
        return _details(store=store, session=session, reply=reply)
    if session.step == STEP_CONFIRM:
        return _confirm(store=store, session=session, reply=reply)
    if session.step == STEP_RESULT:
        # The conversation is over; a further input just closes it.
        return {"prompt": _prompt(STEP_RESULT, session.locale), "step": STEP_RESULT, "done": True}

    raise _invalid_input()


def _menu(*, store: UssdSessionStore, session: UssdSession, reply: str) -> dict[str, object]:
    if reply == MENU_PAY:
        session.step = STEP_SERVICE
        session.done = False
        store.save(session)
        return {
            "prompt": _prompt(STEP_SERVICE, session.locale),
            "step": STEP_SERVICE,
            "done": False,
        }
    if reply == MENU_CHECK:
        return _check_pending(store=store, session=session)
    raise _invalid_input()


def _check_pending(*, store: UssdSessionStore, session: UssdSession) -> dict[str, object]:
    if session.payment_pending:
        session.step = STEP_RESULT
        session.done = True
        store.save(session)
        return {
            "prompt": _prompt("timed_out_pending", session.locale),
            "step": STEP_RESULT,
            "done": True,
        }
    session.step = STEP_RESULT
    session.done = True
    store.save(session)
    return {"prompt": _prompt(STEP_RESULT, session.locale), "step": STEP_RESULT, "done": True}


def _service(*, store: UssdSessionStore, session: UssdSession, reply: str) -> dict[str, object]:
    # The service list is supplied by the gateway, which maps the reply to a
    # service id and resolves the amount out of band; C-036 carries only the
    # conversation, so a reply must be a short menu number, not free text.
    if not reply.isdigit() or len(reply) > 2:
        raise _invalid_input()
    session.step = STEP_DETAILS
    session.done = False
    store.save(session)
    return {"prompt": _prompt(STEP_DETAILS, session.locale), "step": STEP_DETAILS, "done": False}


def _details(*, store: UssdSessionStore, session: UssdSession, reply: str) -> dict[str, object]:
    # The detail (meter or phone number) is the payment recipient. It is held in
    # the session to pass to the payment module and is never echoed in a prompt.
    session.recipient = reply
    session.step = STEP_CONFIRM
    session.done = False
    store.save(session)
    return {"prompt": _prompt(STEP_CONFIRM, session.locale), "step": STEP_CONFIRM, "done": False}


def _confirm(*, store: UssdSessionStore, session: UssdSession, reply: str) -> dict[str, object]:
    if reply.lower() not in AFFIRMATIVE:
        # A decline returns to the menu without authorising anything.
        session.step = STEP_MENU
        session.done = False
        store.save(session)
        return {"prompt": _prompt(STEP_MENU, session.locale), "step": STEP_MENU, "done": False}
    # The affirmative is what C-037 carries; C-036 keeps the session on the
    # confirm step until the separate authorisation call resolves it.
    session.done = False
    store.save(session)
    return {"prompt": _prompt(STEP_CONFIRM, session.locale), "step": STEP_CONFIRM, "done": False}


def authorise(
    *,
    store: UssdSessionStore,
    payments: ChannelPaymentPort,
    session_id: str,
    confirmation: str,
    idempotency_key: str | None,
) -> dict[str, object]:
    """Authorise the payment held by a session (C-037)."""

    if confirmation.strip().lower() not in AFFIRMATIVE:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "The confirmation was not valid.")

    session = store.get(session_id)
    if session is None or session.user_id == "":
        raise APIError(
            400,
            ErrorCode.INVALID_REQUEST,
            "There is no open session to authorise.",
        )

    if is_expired(session, clock=utcnow):
        # A retry past the window: if this session already authorised, the
        # payment is pending and resumes; otherwise nothing was executed.
        resumable = session.authorised
        raise APIError(
            410,
            "session_expired",
            "This session has timed out. The payment is pending; dial again to continue."
            if resumable
            else "This session has timed out before the payment was authorised.",
            {"resumable": resumable},
        )

    if session.authorised:
        # A repeat authorisation of the same session is one payment; report the
        # first outcome rather than authorising again (C-037, duplicate).
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "That payment was already authorised.",
            {"reference": session.payment_reference},
        )

    if not session.service_id or session.amount is None or not session.recipient:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "This session has no payment to authorise.")

    key = idempotency_key or new_id()
    outcome = payments.authorise(
        user_id=session.user_id,
        msisdn=session.msisdn,
        session_id=session.session_id,
        idempotency_key=key,
        service_id=session.service_id,
        recipient=session.recipient,
        amount=session.amount,
        currency=session.currency,
    )

    session.authorised = True
    session.payment_status = outcome.status
    session.payment_reference = outcome.reference
    session.payment_pending = outcome.status == "pending"
    session.step = STEP_RESULT
    session.done = True
    store.save(session)

    return {"status": outcome.status, "reference": outcome.reference}


def attach_payment(
    *,
    session_id: str,
    store: UssdSessionStore,
    service_id: str,
    recipient: str,
    amount: int,
    currency: str = "NGN",
) -> None:
    """Record the payment a session will authorise.

    The USSD gateway resolves the service, amount, and recipient (the assistant
    or the catalogue does the resolution) and hands them to the session before
    the confirmation step; C-036 carries only the conversation. Kept separate
    from :func:`open_or_advance` so the conversation rules stay independent of
    how a payment is resolved.
    """

    session = store.get(session_id)
    if session is None:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "There is no open session.")
    session.service_id = service_id
    session.recipient = recipient
    session.amount = amount
    session.currency = currency
    store.save(session)


def sms_status(
    *,
    sms: SmsDeliveryPort,
    msisdn: str,
    reference: str,
) -> dict[str, object]:
    """Resolve an SMS delivery report scoped to the subscriber (C-038)."""

    message = sms.status(msisdn=msisdn, reference=reference)
    if message is None:
        # A message for another number is indistinguishable from an unknown
        # reference: never leak the existence of another subscriber's message.
        raise APIError(404, ErrorCode.NOT_FOUND, "That reference is not known.")
    return {"reference": message.reference, "status": message.status, "token": message.token}


def deliver_reference(
    *,
    sms: SmsDeliveryPort,
    msisdn: str,
    reference: str,
    token: str | None = None,
) -> None:
    """Queue the reference and token for SMS delivery (FEAT-010).

    Delivery failure does not fail the payment: the message is retained by the
    notification service for retry and its status is readable at C-038. A send
    error is swallowed here so an SMS provider problem never rolls back a
    successful payment.
    """

    body = f"Sabi payment {reference}."
    if token:
        body = f"Sabi payment {reference}. Token {token}."
    message = SmsMessage(reference=reference, msisdn=msisdn, body=body, token=token)
    try:
        sms.send(message=message)
    except (APIError, OSError):
        # A delivery failure is retained for retry at the notification service;
        # the payment outcome is already durable, so a send error never rolls it
        # back (FEAT-010, alternate path C). Anything else is a real bug and is
        # left to surface.
        return


__all__ = [
    "DEFAULT_LOCALE",
    "MENU_CHECK",
    "MENU_PAY",
    "attach_payment",
    "authorise",
    "deliver_reference",
    "open_or_advance",
    "sms_status",
]
