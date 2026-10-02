"""AI-service contract conformance and Phase 1 model-backed acceptance.

Covers C-009 (intent), C-010 (ranking), and C-012 (composition) as the delivered
service exposes them, plus the product behaviors FEAT-003/004/011 and the MQ
refusal rules require. The model is a deterministic double in every test.

Reference: CONTRACTS.md, model-quality.md, features.md.
"""

from __future__ import annotations

from core.config import PRIMARY_MODEL_ID
from core.errors import ProviderUnavailable
from core.testing import FakeModelProvider as _FakeModelProvider
from core.testing import json_response


def scripted(responses):
    return _FakeModelProvider(responses)


def intent_payload(**overrides) -> dict:
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


def valid_stream() -> dict:
    return {
        "messages": [
            {"type": "createSurface", "surfaceId": "confirm-1"},
            {
                "type": "updateComponents",
                "components": [{"component": "ConfirmationSummary", "id": "summary"}],
            },
            {"type": "updateDataModel", "data": {"amount": 500000}},
        ]
    }


# --------------------------------------------------------------------------- #
# C-009 / FEAT-003: a request resolves to a grounded structured intent.
# --------------------------------------------------------------------------- #


def test_pidgin_request_resolves_to_a_bill_payment(ai_client_factory, intent_service) -> None:
    service, provider = intent_service
    provider._responses.append(json_response(intent_payload()))
    with ai_client_factory(intent=service) as client:
        body = client.post(
            "/v1/agent/intents",
            json={"text": "I wan pay my electricity", "locale": "pcm", "channel": "app"},
        ).json()
    assert body["source"] == "model"
    assert body["intent"]["intentType"] == "bill_payment"
    assert body["intent"]["target"] == "svc-electric"
    assert body["intent"]["currency"] == "NGN"


def test_request_naming_a_known_levy_resolves_to_the_agency(
    ai_client_factory, intent_service
) -> None:
    service, provider = intent_service
    provider._responses.append(
        json_response(intent_payload(intent_type="gov_payment", target="svc-landuse"))
    )
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay my land use charge"}).json()
    assert body["intent"]["intentType"] == "gov_payment"
    assert body["intent"]["target"] == "svc-landuse"
    assert any(c["serviceId"] == "svc-landuse" for c in body["candidates"])


def test_unmappable_request_asks_one_question_and_does_not_pay(
    ai_client_factory, intent_service
) -> None:
    """MQ-001 / FEAT-003: below 0.70, ask exactly one question, no payment intent."""

    service, provider = intent_service
    provider._responses.append(json_response(intent_payload(confidence=0.2)))
    with ai_client_factory(intent=service) as client:
        intent = client.post("/v1/agent/intents", json={"text": "help me"}).json()["intent"]
    assert intent["intentType"] not in {"gov_payment", "bill_payment"}
    assert intent["clarifyingQuestion"]
    assert intent["clarifyingQuestion"].count("?") == 1


def test_confidence_just_below_the_cutoff_is_refused(ai_client_factory, intent_service) -> None:
    service, provider = intent_service
    provider._responses.append(json_response(intent_payload(confidence=0.69)))
    with ai_client_factory(intent=service) as client:
        intent = client.post("/v1/agent/intents", json={"text": "pay electricity"}).json()["intent"]
    assert intent["intentType"] == "unknown"
    assert intent["clarifyingQuestion"] is not None


def test_invented_target_is_dropped_and_no_payment_starts(
    ai_client_factory, intent_service
) -> None:
    """Grounding: the model may not name a service the catalogue does not hold."""

    service, provider = intent_service
    provider._responses.append(json_response(intent_payload(target="svc-ghost")))
    with ai_client_factory(intent=service) as client:
        intent = client.post("/v1/agent/intents", json={"text": "pay electricity"}).json()["intent"]
    assert intent["target"] is None
    assert intent["intentType"] == "unknown"


def test_provider_failure_degrades_to_keyword_fallback(ai_client_factory, intent_service) -> None:
    """NFR degradation / FEAT-003 fallback: no 5xx, keyword result, confirmation."""

    service, provider = intent_service
    provider._responses.append(ProviderUnavailable("down"))
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay my electricity"}).json()
    assert body["source"] == "fallback"
    assert body["intent"]["intentType"] == "unknown"
    assert body["intent"]["clarifyingQuestion"] is not None
    assert [c["serviceId"] for c in body["candidates"]] == ["svc-electric"]


def test_intent_wire_fields_are_camel_case(ai_client_factory, intent_service) -> None:
    service, provider = intent_service
    provider._responses.append(json_response(intent_payload()))
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay electricity"}).json()
    assert set(body) == {"intent", "candidates", "source"}
    assert set(body["intent"]) == {
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
    assert "intent_type" not in body["intent"]


# --------------------------------------------------------------------------- #
# C-012 / FEAT-011: interface composition from the client catalogue.
# --------------------------------------------------------------------------- #


def test_composed_confirmation_uses_catalogue_components(
    ai_client_factory, composition_serving
) -> None:
    composition_serving._provider = scripted(
        [json_response(valid_stream(), model_id=PRIMARY_MODEL_ID)]
    )
    with ai_client_factory(composition=composition_serving) as client:
        body = client.post(
            "/v1/agent/surfaces",
            json={"task": "confirmation", "context": {"amount": 500000, "payee": "Ikeja"}},
        ).json()
    assert [m["type"] for m in body["messages"]] == [
        "createSurface",
        "updateComponents",
        "updateDataModel",
    ]
    assert body["fallback"] == "confirmation"


def test_unknown_component_is_refused_and_the_task_stays_completable(
    ai_client_factory, composition_serving
) -> None:
    composition_serving._provider = scripted(
        [
            json_response(
                {
                    "messages": [
                        {
                            "type": "updateComponents",
                            "components": [{"component": "Hologram", "id": "x"}],
                        }
                    ]
                },
                model_id=PRIMARY_MODEL_ID,
            )
        ]
    )
    with ai_client_factory(composition=composition_serving) as client:
        response = client.post("/v1/agent/surfaces", json={"task": "confirmation", "context": {}})
    assert response.status_code == 200
    assert response.json() == {"messages": [], "fallback": "confirmation"}


def test_composition_provider_failure_returns_the_fallback_task(
    ai_client_factory, composition_serving
) -> None:
    composition_serving._provider = scripted([ProviderUnavailable("down")])
    with ai_client_factory(composition=composition_serving) as client:
        body = client.post("/v1/agent/surfaces", json={"task": "receipt", "context": {}}).json()
    assert body == {"messages": [], "fallback": "receipt"}


def test_unknown_task_is_a_400(ai_client_factory) -> None:
    with ai_client_factory() as client:
        response = client.post("/v1/agent/surfaces", json={"task": "run_payment", "context": {}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
