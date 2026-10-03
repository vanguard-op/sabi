"""Unit tests for the USSD/SMS channel gateway (FEAT-010, C-036 to C-038).

The payment module and the notification service are reached through ports, so
these tests bind in-memory stand-ins on ``app.state`` and exercise the session
rules and the contract's shapes, status codes, and errors without a running
payment service or SMS provider. The router is included directly because a test
builds the app before the module discovery is complete; the port seam is the
real integration point.

Session time is billed to airtime, so the timeout path is tested by driving the
injected store's clock past a session's expiry rather than by sleeping
(NFR-006).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import make_settings  # type: ignore[import-not-found]

from app.channels import router as channels_router
from app.channels import service
from app.channels.ports import (
    InMemoryChannelIdentityLookup,
    InMemoryChannelPaymentPort,
    InMemorySmsDeliveryPort,
    PaymentOutcome,
    SmsMessage,
)
from app.channels.sessions import InMemoryUssdSessionStore
from app.core.time import utcnow
from app.main import create_app

MSISDN = "+2348012345678"
SESSION = "ussd-session-1"


@pytest.fixture
def identity() -> InMemoryChannelIdentityLookup:
    lookup = InMemoryChannelIdentityLookup()
    lookup.link(MSISDN, user_id="user-1")
    return lookup


@pytest.fixture
def payments() -> InMemoryChannelPaymentPort:
    return InMemoryChannelPaymentPort()


@pytest.fixture
def sms() -> InMemorySmsDeliveryPort:
    return InMemorySmsDeliveryPort()


@pytest.fixture
def store() -> InMemoryUssdSessionStore:
    return InMemoryUssdSessionStore()


@pytest.fixture
def app(
    identity: InMemoryChannelIdentityLookup,
    payments: InMemoryChannelPaymentPort,
    sms: InMemorySmsDeliveryPort,
    store: InMemoryUssdSessionStore,
) -> Iterator[FastAPI]:
    application = create_app(make_settings())
    application.state.channels_identity = identity
    application.state.channels_payments = payments
    application.state.channels_sms = sms
    application.state.channels_sessions = store
    application.include_router(channels_router.router, prefix="/v1")
    yield application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _open(client: TestClient, *, msisdn: str = MSISDN, session_id: str = SESSION) -> dict:
    response = client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": session_id, "msisdn": msisdn, "input": None, "step": None},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _step(
    client: TestClient,
    *,
    input_value: str,
    step: str,
    session_id: str = SESSION,
    msisdn: str = MSISDN,
) -> dict:
    response = client.post(
        "/v1/channels/ussd/session",
        json={
            "sessionId": session_id,
            "msisdn": msisdn,
            "input": input_value,
            "step": step,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _expire(store: InMemoryUssdSessionStore, session_id: str) -> None:
    """Drive a stored session past its lifetime without sleeping."""

    session = store.get(session_id)
    assert session is not None
    session.expires_at = utcnow() - timedelta(seconds=1)
    store.save(session)


def _attach_payment(store: InMemoryUssdSessionStore) -> None:
    """Attach the payment fields a resolved service would supply at confirm."""

    assert store.get(SESSION) is not None
    service.attach_payment(
        session_id=SESSION,
        store=store,
        service_id="svc-electric",
        recipient="METER-123",
        amount=500000,
    )


# --- C-036: open and drive a session ---------------------------------------


def test_open_linked_number_starts_at_menu(client: TestClient) -> None:
    body = _open(client)
    assert body["step"] == "menu"
    assert body["done"] is False
    assert "1" in body["prompt"]


def test_open_unlinked_number_offers_linking_and_creates_no_account(
    client: TestClient, payments: InMemoryChannelPaymentPort
) -> None:
    body = _open(client, msisdn="+2348099999999")
    assert body["done"] is True
    assert "link" in body["prompt"].lower()
    # An unlinked number never reaches authorisation and never starts a payment.
    assert payments.calls == []


def test_full_conversation_reaches_confirm(client: TestClient) -> None:
    _open(client)
    service_menu = _step(client, input_value="1", step="menu")
    assert service_menu["step"] == "service"
    details = _step(client, input_value="2", step="service")
    assert details["step"] == "details"
    confirm = _step(client, input_value="METER-123", step="details")
    assert confirm["step"] == "confirm"
    assert confirm["done"] is False


def test_driving_another_msisdns_session_conflicts(client: TestClient) -> None:
    _open(client)
    response = client.post(
        "/v1/channels/ussd/session",
        json={
            "sessionId": SESSION,
            "msisdn": "+2348099999999",
            "input": "1",
            "step": "menu",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_out_of_sequence_step_is_rejected(client: TestClient) -> None:
    _open(client)
    response = client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": SESSION, "msisdn": MSISDN, "input": "1", "step": "confirm"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_invalid_menu_reply_is_rejected(client: TestClient) -> None:
    _open(client)
    response = client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": SESSION, "msisdn": MSISDN, "input": "9", "step": "menu"},
    )
    assert response.status_code == 400


def test_expired_session_before_authorisation_is_gone(
    client: TestClient, store: InMemoryUssdSessionStore
) -> None:
    _open(client)
    _expire(store, SESSION)
    response = client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": SESSION, "msisdn": MSISDN, "input": "1", "step": "menu"},
    )
    assert response.status_code == 410
    assert response.json()["error"]["details"]["resumable"] is False


def test_expired_session_after_authorisation_reports_resumable(
    client: TestClient,
    store: InMemoryUssdSessionStore,
    payments: InMemoryChannelPaymentPort,
) -> None:
    # A rail that has not settled yet leaves the payment pending, which is the
    # only state that resumes on the next dial (FEAT-010, alternate path B).
    payments.set_outcome(PaymentOutcome(status="pending", reference="rail-pending-1"))
    _open(client)
    _attach_payment(store)
    response = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "idem-1"},
    )
    assert response.status_code == 200
    _expire(store, SESSION)
    follow_up = client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": SESSION, "msisdn": MSISDN, "input": "1", "step": "menu"},
    )
    assert follow_up.status_code == 410
    assert follow_up.json()["error"]["details"]["resumable"] is True


def test_pending_payment_resumes_on_a_new_session(
    client: TestClient, payments: InMemoryChannelPaymentPort
) -> None:
    payments.set_pending(
        user_id="user-1",
        msisdn=MSISDN,
        outcome=PaymentOutcome(status="pending", reference="rail-pending-1"),
    )
    body = _open(client, session_id="ussd-session-2")
    assert body["step"] == "result"
    assert body["done"] is True
    assert "pending" in body["prompt"].lower()


def test_session_id_is_required(client: TestClient) -> None:
    response = client.post(
        "/v1/channels/ussd/session",
        json={"sessionId": "", "msisdn": MSISDN},
    )
    assert response.status_code == 422


# --- C-037: authorise -------------------------------------------------------


def test_authorise_success_records_payment_and_sends_sms(
    client: TestClient,
    store: InMemoryUssdSessionStore,
    payments: InMemoryChannelPaymentPort,
    sms: InMemorySmsDeliveryPort,
) -> None:
    _open(client)
    _attach_payment(store)

    response = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "idem-success"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "succeeded", "reference": "rail-1"}
    assert len(payments.calls) == 1
    assert payments.calls[0]["service_id"] == "svc-electric"
    assert payments.calls[0]["amount"] == 500000
    # The reference is delivered by SMS and readable at C-038.
    message = sms.status(msisdn=MSISDN, reference="rail-1")
    assert message is not None
    assert message.token is None


def test_sms_failure_does_not_fail_the_payment(
    identity: InMemoryChannelIdentityLookup,
    payments: InMemoryChannelPaymentPort,
    store: InMemoryUssdSessionStore,
) -> None:
    class BrokenSms(InMemorySmsDeliveryPort):
        def send(self, *, message: SmsMessage) -> None:
            raise OSError("provider down")

    application = create_app(make_settings())
    application.state.channels_identity = identity
    application.state.channels_payments = payments
    application.state.channels_sms = BrokenSms()
    application.state.channels_sessions = store
    application.include_router(channels_router.router, prefix="/v1")

    with TestClient(application) as stubborn:
        _open(stubborn)
        _attach_payment(store)
        response = stubborn.post(
            "/v1/channels/ussd/authorise",
            json={"sessionId": SESSION, "confirmation": "1"},
            headers={"Idempotency-Key": "idem-broken-sms"},
        )
    # The payment succeeded even though the SMS provider was down; the message
    # is retained by the notification service for retry (FEAT-010).
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_authorise_without_confirmation_is_rejected(
    client: TestClient, store: InMemoryUssdSessionStore
) -> None:
    _open(client)
    _attach_payment(store)
    response = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "2"},
    )
    assert response.status_code == 400


def test_authorise_without_a_session_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": "missing", "confirmation": "1"},
    )
    assert response.status_code == 400


def test_duplicate_authorisation_conflicts(
    client: TestClient, store: InMemoryUssdSessionStore
) -> None:
    _open(client)
    _attach_payment(store)
    first = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "idem-dup"},
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "idem-dup"},
    )
    assert second.status_code == 409


def test_authorise_after_timeout_reports_pending(
    client: TestClient,
    store: InMemoryUssdSessionStore,
    payments: InMemoryChannelPaymentPort,
) -> None:
    payments.set_outcome(PaymentOutcome(status="pending", reference="rail-pending-2"))
    _open(client)
    _attach_payment(store)
    first = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
        headers={"Idempotency-Key": "idem-timeout"},
    )
    assert first.status_code == 200
    _expire(store, SESSION)
    retry = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
    )
    assert retry.status_code == 410
    assert retry.json()["error"]["details"]["resumable"] is True


def test_authorise_unlinked_session_is_rejected(
    client: TestClient, store: InMemoryUssdSessionStore
) -> None:
    _open(client, msisdn="+2348099999999")
    response = client.post(
        "/v1/channels/ussd/authorise",
        json={"sessionId": SESSION, "confirmation": "1"},
    )
    assert response.status_code == 400


# --- C-038: SMS status ------------------------------------------------------
#
# Revision 2: the subscriber is resolved server-side from the MSISDN-bound
# session established by C-036. The caller presents the sessionId it holds; the
# number comes from the store, never from a client-supplied header. These tests
# open a real session through C-036 to establish that binding.


def _bind_session(client: TestClient, *, msisdn: str = MSISDN, session_id: str = SESSION) -> None:
    """Open a C-036 session so its MSISDN is bound server-side."""

    _open(client, msisdn=msisdn, session_id=session_id)


def test_sms_status_returns_own_message(client: TestClient, sms: InMemorySmsDeliveryPort) -> None:
    sms.send(
        message=SmsMessage(
            reference="ref-1",
            msisdn=MSISDN,
            body="Sabi payment ref-1.",
            status="delivered",
            token=None,
        )
    )
    _bind_session(client)
    response = client.get(f"/v1/channels/sms/status/ref-1?sessionId={SESSION}")
    assert response.status_code == 200
    assert response.json() == {"reference": "ref-1", "status": "delivered", "token": None}


def test_sms_status_returns_token_when_present(
    client: TestClient, sms: InMemorySmsDeliveryPort
) -> None:
    sms.send(
        message=SmsMessage(
            reference="ref-token",
            msisdn=MSISDN,
            body="Sabi token.",
            status="sent",
            token="4567-8901",
        )
    )
    _bind_session(client)
    response = client.get(f"/v1/channels/sms/status/ref-token?sessionId={SESSION}")
    assert response.status_code == 200
    assert response.json()["token"] == "4567-8901"


def test_sms_status_hides_another_subscribers_message(
    client: TestClient, sms: InMemorySmsDeliveryPort
) -> None:
    sms.send(message=SmsMessage(reference="ref-2", msisdn="+2348011111111", body="Private."))
    _bind_session(client)
    response = client.get(f"/v1/channels/sms/status/ref-2?sessionId={SESSION}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_sms_status_unknown_reference(client: TestClient) -> None:
    _bind_session(client)
    response = client.get(f"/v1/channels/sms/status/nope?sessionId={SESSION}")
    assert response.status_code == 404


def test_sms_status_without_a_bound_session_is_unknown(client: TestClient) -> None:
    response = client.get("/v1/channels/sms/status/ref-1")
    assert response.status_code == 404


def test_sms_status_ignores_a_client_supplied_msisdn_header(
    client: TestClient, sms: InMemorySmsDeliveryPort
) -> None:
    # The forged header names the true subscriber, but identity is bound to the
    # session, so a caller with no session cannot read the message (NFR-020).
    sms.send(message=SmsMessage(reference="ref-3", msisdn=MSISDN, body="Private."))
    response = client.get(
        "/v1/channels/sms/status/ref-3",
        headers={"X-Channel-Msisdn": MSISDN},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_sms_status_rejects_another_subscribers_session(
    client: TestClient, sms: InMemorySmsDeliveryPort
) -> None:
    # The message belongs to MSISDN, but the caller holds a session bound to a
    # different number, so it resolves as unknown rather than leaking status.
    sms.send(message=SmsMessage(reference="ref-4", msisdn=MSISDN, body="Private."))
    _bind_session(client, msisdn="+2348099999999", session_id="other-session")
    response = client.get("/v1/channels/sms/status/ref-4?sessionId=other-session")
    assert response.status_code == 404
