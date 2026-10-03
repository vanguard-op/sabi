"""Phase 2 integration and acceptance: the USSD and SMS channel.

The USSD/SMS surface authenticates a channel identity, not an app session, and
reaches identity, payments, and SMS delivery through ports the deployment binds
on ``app.state``. This module drives the mounted C-036/C-037/C-038 surface on
the assembled API service end to end: open a session, walk it to confirmation,
authorise, and read the delivered reference back.

The payment the session authorises is resolved out of band by the USSD gateway
(the assistant or the catalogue does the resolution), represented here by the
same ``attach_payment`` call a production channel gateway makes.

Reference: features.md FEAT-010, user-flow.md Flow 4, CONTRACTS.md C-036..C-038,
nfr.md NFR-006.
"""

from __future__ import annotations

from datetime import timedelta

from app.channels import service as channel_service
from app.channels.ports import PaymentOutcome
from app.core.time import utcnow

MSISDN = "+2348012345678"
SESSION = "ussd-session-gate"


def _open(client, *, msisdn: str = MSISDN, session_id: str = SESSION):
    return client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": session_id, "msisdn": msisdn, "input": None, "step": None},
    )


def _step(client, *, input_value: str, step: str, session_id: str = SESSION, msisdn: str = MSISDN):
    return client.post(
        "/v1/channels/ussd/session",
        json={
            "sessionId": session_id,
            "msisdn": msisdn,
            "input": input_value,
            "step": step,
        },
    )


def test_a_linked_number_walks_the_conversation_to_confirmation(api_client, channel_ports):
    """FEAT-010 acceptance 1: a feature-phone user can start a payment by USSD."""

    channel_ports["identity"].link(MSISDN, user_id="user-1", locale="pcm")

    opened = _open(api_client)
    assert opened.status_code == 200, opened.text
    assert opened.json()["step"] == "menu"
    assert opened.json()["done"] is False

    assert _step(api_client, input_value="1", step="menu").json()["step"] == "service"
    assert _step(api_client, input_value="1", step="service").json()["step"] == "details"
    confirm = _step(api_client, input_value="METER-123", step="details")
    assert confirm.json()["step"] == "confirm"


def test_an_unlinked_number_creates_no_account_and_cannot_pay(api_client, channel_ports):
    """FEAT-010 / FEAT-001: a channel link never creates a second account."""

    opened = _open(api_client, msisdn="+2348099999999")
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["done"] is True
    assert "link" in body["prompt"].lower()

    # No account was minted, so authorising would be rejected: the session has no
    # linked owner.
    authorise = api_client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "ussd-unlinked"},
    )
    assert authorise.status_code == 400


def test_authorising_a_walked_session_settles_and_delivers_the_reference_by_sms(
    api_client, channel_ports
):
    """FEAT-010 acceptance 3: the reference arrives by SMS on success."""

    channel_ports["identity"].link(MSISDN, user_id="user-1")
    channel_ports["payments"].set_outcome(
        PaymentOutcome(status="succeeded", reference="SBX-USSD-1", payment_id="pay-ussd")
    )

    _open(api_client)
    _step(api_client, input_value="1", step="menu")
    _step(api_client, input_value="1", step="service")
    _step(api_client, input_value="METER-123", step="details")

    # The channel gateway resolves the payment out of band before authorisation.
    channel_service.attach_payment(
        session_id=SESSION,
        store=api_client.app.state.channels_sessions,
        service_id="svc-electric",
        recipient="METER-123",
        amount=500_000,
    )

    authorised = api_client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "ussd-1"},
    )
    assert authorised.status_code == 200, authorised.text
    body = authorised.json()
    assert body["status"] == "succeeded"
    assert body["reference"] == "SBX-USSD-1"

    # The reference is queued for SMS and readable at C-038 by the bound session.
    status = api_client.get(
        "/v1/channels/sms/status/SBX-USSD-1",
        params={"sessionId": SESSION},
    )
    assert status.status_code == 200, status.text
    assert status.json()["reference"] == "SBX-USSD-1"
    assert status.json()["status"] in {"queued", "sent", "delivered"}


def test_duplicate_authorisation_of_a_session_is_a_conflict(api_client, channel_ports):
    """FEAT-010 edge: a repeated authorisation executes once."""

    channel_ports["identity"].link(MSISDN, user_id="user-1")
    channel_ports["payments"].set_outcome(PaymentOutcome(status="succeeded", reference="SBX-D"))

    _open(api_client)
    _step(api_client, input_value="1", step="menu")
    _step(api_client, input_value="1", step="service")
    _step(api_client, input_value="METER-123", step="details")
    channel_service.attach_payment(
        session_id=SESSION,
        store=api_client.app.state.channels_sessions,
        service_id="svc-electric",
        recipient="METER-123",
        amount=500_000,
    )

    first = api_client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "ussd-dup"},
    )
    assert first.status_code == 200

    second = api_client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "ussd-dup"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_a_session_timed_out_after_authorisation_resumes_the_pending_payment(
    api_client, channel_ports
):
    """FEAT-010 acceptance 2: a timed-out session resumes, not restarts."""

    channel_ports["identity"].link(MSISDN, user_id="user-1")
    channel_ports["payments"].set_outcome(PaymentOutcome(status="pending", reference="SBX-P"))
    channel_ports["payments"].set_pending(
        user_id="user-1", msisdn=MSISDN, outcome=PaymentOutcome(status="pending", reference="SBX-P")
    )

    # A fresh session for a number with a pending payment reports it at result.
    resumed = _open(api_client)
    assert resumed.status_code == 200
    assert resumed.json()["step"] == "result"
    assert resumed.json()["done"] is True
    assert "pending" in resumed.json()["prompt"].lower()


def test_sms_status_without_a_bound_session_is_unknown(api_client, channel_ports):
    """C-038 revision 2: ownership is resolved server-side, never from a header."""

    channel_ports["identity"].link(MSISDN, user_id="user-1")

    response = api_client.get("/v1/channels/sms/status/SBX-UNKNOWN")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    # An inbound MSISDN header is attacker-controlled and must be ignored.
    spoofed = api_client.get(
        "/v1/channels/sms/status/SBX-UNKNOWN",
        headers={"X-MSISDN": MSISDN, "X-Sabi-Msisdn": MSISDN},
    )
    assert spoofed.status_code == 404


def test_an_expired_session_before_authorisation_executes_nothing(api_client, channel_ports):
    """FEAT-010 alternate A: timeout before authorisation means no payment."""

    channel_ports["identity"].link(MSISDN, user_id="user-1")
    _open(api_client)

    store = api_client.app.state.channels_sessions
    session = store.get(SESSION)
    session.expires_at = utcnow() - timedelta(seconds=1)
    store.save(session)

    response = _step(api_client, input_value="1", step="menu")
    assert response.status_code == 410
    assert channel_ports["payments"].calls == [], "a payment was authorised after timeout"
