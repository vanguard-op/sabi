"""Unit tests for the USSD/SMS aggregator adapter (FEAT-010, C-036 to C-038).

The adapter is the translation layer between the mobile-network/USSD/SMS
aggregator wire format and the channel gateway. These tests pin the real
mechanism the aggregator uses — the subscriber's MSISDN arrives in the callback
payload, not an ``X-Channel-Msisdn`` header — and the two directions the
adapter owns: reading an inbound callback into the C-036 fields and rendering
the gateway's answer back as ``CON``/``END``, and delivering SMS with a status
readable at C-038.

The transport is faked, so no aggregator is required.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import make_settings  # type: ignore[import-not-found]

from app.channels import router as channels_router
from app.channels.aggregator.callback import (
    CallbackPayloadError,
    parse_delivery_report,
    parse_ussd_callback,
    render_ussd_response,
)
from app.channels.aggregator.client import (
    AggregatorEndpoint,
    AggregatorUnavailable,
)
from app.channels.aggregator.sms import AggregatorSmsDeliveryPort
from app.channels.aggregator.wiring import (
    CLIENT_STATE_KEY,
    SMS_PORT_STATE_KEY,
    bind_aggregator,
)
from app.channels.ports import (
    InMemoryChannelIdentityLookup,
    InMemoryChannelPaymentPort,
    SmsMessage,
)
from app.channels.sessions import InMemoryUssdSessionStore
from app.main import create_app

MSISDN = "+2348012345678"


class FakeAggregatorClient:
    """Records sends and can be made to fail like a provider outage."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sends: list[dict[str, str]] = []
        self._fail = fail

    def send_sms(self, *, msisdn: str, body: str, sender_id: str | None = None) -> None:
        if self._fail:
            raise AggregatorUnavailable()
        self.sends.append({"msisdn": msisdn, "body": body})


# --- Inbound USSD callback --------------------------------------------------


def test_parse_form_callback_takes_the_number_from_the_payload() -> None:
    # The aggregator posts the subscriber's number as a form field, so no
    # X-Channel-Msisdn header is involved.
    callback = parse_ussd_callback(
        {
            "sessionId": "ATUid_abc123",
            "serviceCode": "*123#",
            "phoneNumber": MSISDN,
            "text": "",
        }
    )
    assert callback.session_id == "ATUid_abc123"
    assert callback.msisdn == MSISDN
    assert callback.service_code == "*123#"
    assert callback.input_value is None  # first call: only dialled


def test_parse_json_callback_uses_msisdn_field() -> None:
    callback = parse_ussd_callback({"sessionId": "s-1", "msisdn": MSISDN, "input": "2"})
    assert callback.msisdn == MSISDN
    assert callback.input_value == "2"


def test_parse_callback_takes_the_last_input_from_a_cumulative_path() -> None:
    # The aggregator concatenates the keypad path with "*"; the gateway wants the
    # single answer that produced this call.
    callback = parse_ussd_callback({"sessionId": "s-1", "phoneNumber": MSISDN, "text": "1*2*3"})
    assert callback.input_value == "3"


def test_parse_callback_missing_number_is_rejected() -> None:
    with pytest.raises(CallbackPayloadError, match="phoneNumber"):
        parse_ussd_callback({"sessionId": "s-1", "text": "1"})


def test_parse_callback_missing_session_is_rejected() -> None:
    with pytest.raises(CallbackPayloadError, match="sessionId"):
        parse_ussd_callback({"phoneNumber": MSISDN})


def test_callback_builds_the_gateway_request_shape() -> None:
    callback = parse_ussd_callback(
        {"sessionId": "ATUid_abc123", "phoneNumber": MSISDN, "text": "7"}
    )
    request = callback.to_session_request()
    # C-036 field names are camelCase on the wire.
    assert request.session_id == "ATUid_abc123"
    assert request.msisdn == MSISDN
    assert request.input == "7"


def test_render_response_continues_and_ends() -> None:
    assert render_ussd_response(prompt="Sabi. 1 Pay. 2 Check.", done=False).startswith("CON ")
    assert render_ussd_response(prompt="Done.", done=True).startswith("END ")


def test_render_response_always_carries_a_prefix() -> None:
    # A response with no CON/END prefix makes the aggregator drop the session.
    assert render_ussd_response(prompt="", done=False) == "CON"
    assert render_ussd_response(prompt="   ", done=True) == "END"


# --- Inbound SMS delivery report -------------------------------------------


def test_parse_delivery_report_normalises_success_to_delivered() -> None:
    report = parse_delivery_report(
        {"id": "ATXid_1", "status": "Success", "phoneNumber": MSISDN, "retryCount": "0"}
    )
    assert report.reference == "ATXid_1"
    assert report.msisdn == MSISDN
    assert report.status == "delivered"


def test_parse_delivery_report_carries_failure_status_and_reason() -> None:
    report = parse_delivery_report(
        {
            "id": "ATXid_2",
            "status": "Failed",
            "phoneNumber": MSISDN,
            "failureReason": "Absent Subscriber",
        }
    )
    assert report.status == "failed"
    assert report.reason == "Absent Subscriber"


def test_parse_delivery_report_unknown_status_is_queued() -> None:
    report = parse_delivery_report({"id": "x", "status": "Weird", "phoneNumber": MSISDN})
    assert report.status == "queued"


def test_parse_delivery_report_requires_reference_and_number() -> None:
    with pytest.raises(CallbackPayloadError):
        parse_delivery_report({"status": "Success", "phoneNumber": MSISDN})
    with pytest.raises(CallbackPayloadError):
        parse_delivery_report({"id": "x", "status": "Success"})


# --- Outbound SMS delivery port (C-038) ------------------------------------


def _message(reference: str = "ref-1", msisdn: str = MSISDN) -> SmsMessage:
    return SmsMessage(reference=reference, msisdn=msisdn, body=f"Sabi payment {reference}.")


def test_send_posts_to_the_aggregator_and_is_readable() -> None:
    client = FakeAggregatorClient()
    port = AggregatorSmsDeliveryPort(client=client)
    port.send(message=_message())

    assert client.sends == [{"msisdn": MSISDN, "body": "Sabi payment ref-1."}]
    stored = port.status(msisdn=MSISDN, reference="ref-1")
    assert stored is not None
    assert stored.status == "queued"
    assert stored.created_at is not None


def test_status_hides_another_subscribers_message() -> None:
    port = AggregatorSmsDeliveryPort(client=FakeAggregatorClient())
    port.send(message=_message(msisdn="+2348099999999"))
    # A number that does not own the message resolves as unknown, exactly as a
    # missing reference does, so existence is not inferable.
    assert port.status(msisdn=MSISDN, reference="ref-1") is None


def test_status_unknown_reference_is_none() -> None:
    port = AggregatorSmsDeliveryPort(client=FakeAggregatorClient())
    assert port.status(msisdn=MSISDN, reference="nope") is None


def test_delivery_report_updates_status_and_keeps_token() -> None:
    port = AggregatorSmsDeliveryPort(client=FakeAggregatorClient())
    port.send(message=SmsMessage(reference="ref-t", msisdn=MSISDN, body="Token.", token="4567"))

    port.record_report(
        parse_delivery_report({"id": "ref-t", "status": "Success", "phoneNumber": MSISDN})
    )
    stored = port.status(msisdn=MSISDN, reference="ref-t")
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.token == "4567"


def test_report_for_another_number_does_not_mutate_the_message() -> None:
    port = AggregatorSmsDeliveryPort(client=FakeAggregatorClient())
    port.send(message=_message())
    port.record_report(
        parse_delivery_report({"id": "ref-1", "status": "Success", "phoneNumber": "+2348099999999"})
    )
    stored = port.status(msisdn=MSISDN, reference="ref-1")
    assert stored is not None
    assert stored.status == "queued"


def test_report_arriving_before_the_send_settles_the_message() -> None:
    port = AggregatorSmsDeliveryPort(client=FakeAggregatorClient())
    port.record_report(
        parse_delivery_report({"id": "ref-2", "status": "Success", "phoneNumber": MSISDN})
    )
    port.send(message=_message(reference="ref-2"))
    stored = port.status(msisdn=MSISDN, reference="ref-2")
    assert stored is not None
    assert stored.status == "delivered"


def test_send_failure_retains_the_message_for_retry() -> None:
    port = AggregatorSmsDeliveryPort(client=FakeAggregatorClient(fail=True))
    # The gateway treats the failure as retained-for-retry; the port still holds
    # the message so C-038 answers meanwhile (FEAT-010, alternate path C).
    with pytest.raises(AggregatorUnavailable):
        port.send(message=_message())
    assert port.status(msisdn=MSISDN, reference="ref-1") is not None


def test_port_without_a_client_retains_queued() -> None:
    port = AggregatorSmsDeliveryPort()
    port.send(message=_message())
    stored = port.status(msisdn=MSISDN, reference="ref-1")
    assert stored is not None
    assert stored.status == "queued"


# --- Wiring -----------------------------------------------------------------


def test_bind_aggregator_sets_the_gateway_port_when_absent() -> None:
    app = SimpleNamespace(state=SimpleNamespace())
    bind_aggregator(app, SimpleNamespace(environment="development"))
    port = getattr(app.state, SMS_PORT_STATE_KEY)
    assert isinstance(port, AggregatorSmsDeliveryPort)
    # The client is exposed so the app's lifespan can close it.
    assert getattr(app.state, CLIENT_STATE_KEY) is port.client


def test_bind_aggregator_does_not_replace_an_existing_port() -> None:
    existing = AggregatorSmsDeliveryPort()
    app = SimpleNamespace(state=SimpleNamespace(**{SMS_PORT_STATE_KEY: existing}))
    bind_aggregator(app, SimpleNamespace(environment="development"))
    assert getattr(app.state, SMS_PORT_STATE_KEY) is existing


# --- Endpoint configuration -------------------------------------------------


def test_endpoint_reads_env_override_and_api_key() -> None:
    endpoint = AggregatorEndpoint.from_env(
        {
            "AGGREGATOR_BASE_URL": "https://aggregator.example/",
            "AGGREGATOR_API_KEY": "secret-value",
            "AGGREGATOR_SENDER_ID": "SABI",
        }
    )
    assert endpoint.base_url == "https://aggregator.example"
    assert endpoint.api_key == "secret-value"
    assert endpoint.sender_id == "SABI"


def test_endpoint_defaults_without_configuration() -> None:
    endpoint = AggregatorEndpoint.from_env({})
    assert endpoint.base_url.startswith("http://")
    assert endpoint.send_path
    assert endpoint.timeout_seconds > 0


# --- Adapter to gateway seam ------------------------------------------------


@pytest.fixture
def gateway() -> Iterator[FastAPI]:
    """The mounted channel gateway with the adapter's SMS port behind it."""

    identity = InMemoryChannelIdentityLookup()
    identity.link(MSISDN, user_id="user-1")
    application = create_app(make_settings())
    application.state.channels_identity = identity
    application.state.channels_payments = InMemoryChannelPaymentPort()
    application.state.channels_sms = AggregatorSmsDeliveryPort(client=FakeAggregatorClient())
    application.state.channels_sessions = InMemoryUssdSessionStore()
    application.include_router(channels_router.router, prefix="/v1")
    yield application


def test_inbound_callback_drives_the_gateway_and_renders_con(gateway: FastAPI) -> None:
    # The aggregator's form callback is translated into the C-036 fields and the
    # gateway's answer is rendered back with a CON prefix, all in one hop.
    callback = parse_ussd_callback({"sessionId": "s-1", "phoneNumber": MSISDN, "text": ""})
    with TestClient(gateway) as client:
        response = client.post(
            "/v1/channels/ussd/session",
            json=callback.to_session_request().model_dump(by_alias=True),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["done"] is False
    assert body["step"] == "menu"
    assert render_ussd_response(prompt=body["prompt"], done=body["done"]).startswith("CON ")


def test_gateway_sends_reference_through_the_adapter_and_reports_it(
    gateway: FastAPI,
) -> None:
    # The gateway's deliver_reference reaches the aggregator port; the retained
    # message is readable at C-038, which is the delivery surface the aggregator
    # backs.
    from app.channels import service

    store = gateway.state.channels_sessions
    with TestClient(gateway) as client:
        client.post(
            "/v1/channels/ussd/session",
            json={"sessionId": "s-1", "msisdn": MSISDN, "input": None, "step": None},
        )
        service.attach_payment(
            session_id="s-1",
            store=store,
            service_id="svc-electric",
            recipient="METER-1",
            amount=500000,
        )
        client.post(
            "/v1/channels/ussd/authorise",
            json={"sessionId": "s-1", "confirmation": "1"},
            headers={"Idempotency-Key": "idem-agg"},
        )
        status = client.get(
            "/v1/channels/sms/status/rail-1",
            headers={"X-Channel-Msisdn": MSISDN},
        )
    # C-038's header is a Sabi-internal scoping credential; the aggregator's own
    # mechanism is the callback payload parsed above, so this confirms the port
    # the adapter supplies answers the contract's delivery read.
    assert status.status_code == 200
    assert status.json()["reference"] == "rail-1"
