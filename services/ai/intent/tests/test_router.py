"""HTTP conformance tests for intent resolution (C-009).

The model is a deterministic double injected through FastAPI's dependency override,
so no network call or SDK is involved. These protect the frozen wire contract and the
product behaviors FEAT-003 and MQ-001 require: a grounded structured intent, exactly
one clarifying question below the 0.70 cutoff, no invented target or amount, and the
documented keyword fallback when the provider fails.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.errors import ModelTimeout, ProviderUnavailable
from core.serving import ModelServing
from core.testing import FakeModelProvider, json_response, text_response
from intent.deps import get_intent_service
from intent.service import IntentService

ENDPOINT = "/v1/agent/intents"


def _intent_payload(**overrides):
    payload = {
        "intent_type": "bill_payment",
        "target": "svc-electric",
        "amount": None,
        "currency": "NGN",
        "reference": None,
        "constraints": {},
        "confidence": 0.95,
        "language": "en",
        "clarifying_question": None,
        "detected_language": None,
    }
    payload.update(overrides)
    return payload


def _service(
    catalogue, responses=None, *, responder=None
) -> tuple[IntentService, FakeModelProvider]:
    provider = FakeModelProvider(responses, responder=responder)
    return IntentService(ModelServing(provider, catalogue)), provider


@contextmanager
def _client(service) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_intent_service] = lambda: service
    with TestClient(app) as client:
        yield client


# --- Contract conformance --------------------------------------------------------


def test_resolves_a_grounded_intent_with_camel_case_fields(catalogue):
    service, provider = _service(catalogue, [json_response(_intent_payload(amount=500000))])
    with _client(service) as client:
        response = client.post(
            ENDPOINT,
            json={"text": "pay my electricity 5,000", "locale": "en", "channel": "app"},
        )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"intent", "candidates", "source"}
    assert body["source"] == "model"
    intent = body["intent"]
    assert set(intent) == {
        "intentType",
        "target",
        "amount",
        "currency",
        "reference",
        "constraints",
        "confidence",
        "language",
        "clarifyingQuestion",
    }
    assert intent["intentType"] == "bill_payment"
    assert intent["target"] == "svc-electric"
    assert intent["amount"] == 500000
    assert intent["currency"] == "NGN"
    assert intent["confidence"] == 0.95
    assert intent["clarifyingQuestion"] is None
    # The model-internal snake_case schema never crosses the boundary (D-018).
    assert "intent_type" not in intent
    assert provider.last_request.prompt_version == "v1"


def test_candidates_carry_the_service_summary_wire_shape(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload())])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()
    assert body["candidates"]
    candidate = body["candidates"][0]
    assert set(candidate) == {
        "serviceId",
        "name",
        "collectingBody",
        "category",
        "knownAmount",
        "currency",
        "status",
        "confidence",
    }
    assert candidate["serviceId"] == "svc-electric"


def test_locale_and_channel_default_when_omitted(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(intent_type="unknown"))])
    with _client(service) as client:
        response = client.post(ENDPOINT, json={"text": "hello"})
    assert response.status_code == 200
    assert response.json()["source"] == "model"


def test_pidgin_request_resolves(catalogue):
    # FEAT-003 acceptance: "I wan pay my electricity" resolves to the electricity biller.
    service, _ = _service(catalogue, [json_response(_intent_payload(intent_type="bill_payment"))])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": "I wan pay my electricity"}).json()
    assert body["intent"]["intentType"] == "bill_payment"
    assert body["intent"]["target"] == "svc-electric"


@pytest.mark.parametrize("channel", ["app", "ussd", "sms", "whatsapp"])
def test_every_contract_channel_is_accepted(catalogue, channel):
    service, _ = _service(catalogue, [json_response(_intent_payload())])
    with _client(service) as client:
        response = client.post(ENDPOINT, json={"text": "pay light", "channel": channel})
    assert response.status_code == 200


# --- 400 validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("text", ""),
        ("text", "   "),
        ("text", "x" * 201),
        ("locale", "fr"),
        ("channel", "email"),
    ],
)
def test_invalid_request_fields_are_rejected_400(catalogue, field, value):
    service, _ = _service(catalogue, [json_response(_intent_payload())])
    payload = {"text": "pay light", "locale": "en", "channel": "app"}
    payload[field] = value
    with _client(service) as client:
        response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 400


def test_missing_text_is_rejected_400(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload())])
    with _client(service) as client:
        response = client.post(ENDPOINT, json={"locale": "en", "channel": "app"})
    assert response.status_code == 400


def test_over_length_text_is_a_contract_error_not_a_model_call(catalogue):
    service, provider = _service(catalogue, [json_response(_intent_payload())])
    with _client(service) as client:
        response = client.post(ENDPOINT, json={"text": "x" * 201})
    assert response.status_code == 400
    assert provider.requests == []


def test_validation_error_uses_the_shared_envelope(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload())])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": ""}).json()
    assert set(body) == {"error"}
    assert set(body["error"]) <= {"code", "message", "details"}
    assert isinstance(body["error"]["code"], str)
    assert isinstance(body["error"]["message"], str)


# --- Refusal: the 0.70 cutoff -----------------------------------------------------


def test_low_confidence_payment_asks_exactly_one_question_and_does_not_pay(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(confidence=0.3))])
    with _client(service) as client:
        intent = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()["intent"]
    assert intent["intentType"] == "unknown"
    assert intent["clarifyingQuestion"] is not None
    assert intent["clarifyingQuestion"].count("?") == 1
    assert intent["intentType"] not in {"gov_payment", "bill_payment"}


def test_confidence_just_below_the_cutoff_is_refused(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(confidence=0.69))])
    with _client(service) as client:
        intent = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()["intent"]
    assert intent["intentType"] == "unknown"
    assert intent["clarifyingQuestion"] is not None


def test_confidence_at_the_cutoff_resolves(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(confidence=0.70))])
    with _client(service) as client:
        intent = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()["intent"]
    assert intent["intentType"] == "bill_payment"
    assert intent["clarifyingQuestion"] is None


# --- No invention -----------------------------------------------------------------


def test_invented_target_is_dropped_and_payment_collapses(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(target="svc-ghost"))])
    with _client(service) as client:
        intent = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()["intent"]
    assert intent["target"] is None
    assert intent["intentType"] == "unknown"
    assert intent["clarifyingQuestion"] is not None


def test_untraceable_amount_is_dropped(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(amount=999999))])
    with _client(service) as client:
        intent = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()["intent"]
    assert intent["amount"] is None


def test_a_user_stated_amount_in_kobo_is_kept(catalogue):
    service, _ = _service(catalogue, [json_response(_intent_payload(amount=500000))])
    with _client(service) as client:
        intent = client.post(ENDPOINT, json={"text": "pay my electricity five thousand"}).json()[
            "intent"
        ]
    assert intent["amount"] == 500000


# --- Fallback (provider unavailable / timeout / unusable) --------------------------


def test_provider_unavailable_degrades_to_keyword_fallback(catalogue):
    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()
    assert body["source"] == "fallback"
    assert body["intent"]["intentType"] == "unknown"
    assert body["intent"]["confidence"] == 0.0
    assert body["intent"]["clarifyingQuestion"] is not None
    assert [item["serviceId"] for item in body["candidates"]] == ["svc-electric"]


def test_provider_timeout_degrades_to_keyword_fallback(catalogue):
    service, _ = _service(catalogue, [ModelTimeout("slow")])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()
    assert body["source"] == "fallback"
    assert body["intent"]["intentType"] == "unknown"


def test_unparseable_output_degrades_to_keyword_fallback(catalogue):
    service, _ = _service(catalogue, [text_response("not json")])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": "pay my electricity"}).json()
    assert body["source"] == "fallback"
    assert body["intent"]["intentType"] == "unknown"


def test_fallback_never_invents_a_target_when_the_catalogue_misses(catalogue):
    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    with _client(service) as client:
        body = client.post(ENDPOINT, json={"text": "pay my airtime topup"}).json()
    assert body["source"] == "fallback"
    assert body["candidates"] == []
    assert body["intent"]["target"] is None
    assert body["intent"]["clarifyingQuestion"] is not None
