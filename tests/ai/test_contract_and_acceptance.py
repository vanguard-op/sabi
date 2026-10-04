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
    """The MQ-001 model output: an authored ``reply`` plus the reduced intent.

    Revision 4 folds the clarifying question and the greeting into ``reply`` and
    carries only machine-actionable fields on the intent. ``detected_language`` stays
    in the structured output as the language signal the client and MQ-004 consume.
    """

    payload = {
        "reply": "I've got Ikeja Electric. Confirm and I'll prepare it.",
        "intent_type": "bill_payment",
        "target": "svc-electric",
        "amount": None,
        "currency": "NGN",
        "reference": None,
        "constraints": {},
        "confidence": 0.95,
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
    """MQ-001 / FEAT-003: below 0.70, one question, no payment intent.

    The clarifying question is the model-authored ``reply`` in revision 4, not a
    separate field, so the "at most one question" assertion reads the reply.
    """

    service, provider = intent_service
    provider._responses.append(
        json_response(
            intent_payload(
                confidence=0.2,
                reply="Which service or biller do you want to pay?",
            )
        )
    )
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "help me"}).json()
    assert body["intent"]["intentType"] not in {"gov_payment", "bill_payment"}
    assert body["reply"]
    assert body["reply"].count("?") == 1
    assert "clarifyingQuestion" not in body["intent"]


def test_confidence_just_below_the_cutoff_is_refused(ai_client_factory, intent_service) -> None:
    service, provider = intent_service
    provider._responses.append(
        json_response(intent_payload(confidence=0.69, reply="Which one did you mean?"))
    )
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay electricity"}).json()
    assert body["intent"]["intentType"] == "unknown"
    # The follow-up travels in the reply; the refusal register is honest about the
    # request rather than framing the platform as limited (D-046).
    assert body["reply"] is not None
    assert "question" not in body["intent"]


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
    """NFR degradation / FEAT-003 fallback: no 5xx, keyword result, confirmation.

    The degraded path authors no reply, so the client renders its prewritten
    fallback for the state; the keyword match still travels as candidates for
    confirmation (MQ-001 Fallback).
    """

    service, provider = intent_service
    provider._responses.append(ProviderUnavailable("down"))
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay my electricity"}).json()
    assert body["source"] == "fallback"
    assert body["intent"]["intentType"] == "unknown"
    assert body["reply"] is None
    assert [c["serviceId"] for c in body["candidates"]] == ["svc-electric"]


def test_non_command_greeting_is_not_a_coverage_miss(ai_client_factory, intent_service) -> None:
    """MQ-001 / FEAT-003: a greeting is ``non_command``, answered conversationally,
    with no payment field, no clarifying question, and no candidates recorded."""

    service, provider = intent_service
    provider._responses.append(
        json_response(
            intent_payload(
                intent_type="non_command",
                target=None,
                confidence=1.0,
                reply="I can help you pay levies and bills. What would you like to do?",
            )
        )
    )
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "Hello"}).json()
    assert body["intent"]["intentType"] == "non_command"
    assert body["intent"]["target"] is None
    assert body["intent"]["amount"] is None
    assert body["candidates"] == []
    assert body["reply"] == "I can help you pay levies and bills. What would you like to do?"


def test_a_null_reply_reaches_the_client_unchanged(ai_client_factory, intent_service) -> None:
    """A missing model reply is null so the client renders its prewritten fallback."""

    service, provider = intent_service
    provider._responses.append(json_response(intent_payload(reply=None)))
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay electricity"}).json()
    assert body["reply"] is None
    assert body["source"] == "model"


def test_intent_wire_fields_are_camel_case(ai_client_factory, intent_service) -> None:
    service, provider = intent_service
    provider._responses.append(json_response(intent_payload()))
    with ai_client_factory(intent=service) as client:
        body = client.post("/v1/agent/intents", json={"text": "pay electricity"}).json()
    assert set(body) == {"reply", "intent", "candidates", "source"}
    assert set(body["intent"]) == {
        "intentType",
        "target",
        "amount",
        "currency",
        "reference",
        "constraints",
        "confidence",
        "detectedLanguage",
    }
    assert "intent_type" not in body["intent"]
    # Revision 4 removed the separate language and clarifyingQuestion fields.
    assert "language" not in body["intent"]
    assert "clarifyingQuestion" not in body["intent"]


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
