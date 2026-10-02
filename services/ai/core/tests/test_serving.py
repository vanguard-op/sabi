from __future__ import annotations

from core.config import FLASH_MODEL_ID
from core.errors import ProviderUnavailable
from core.serving import ModelServing
from core.testing import FakeModelProvider, json_response, text_response


def _serving(catalogue, responses=None, *, responder=None):
    provider = FakeModelProvider(responses, responder=responder)
    return ModelServing(provider, catalogue), provider


def _intent(**overrides):
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


# --- MQ-001 intent resolution ----------------------------------------------------


def test_resolve_intent_returns_a_grounded_model_result(catalogue):
    serving, provider = _serving(
        catalogue,
        [json_response(_intent(amount=500000))],
    )
    result = serving.resolve_intent("pay my electricity 5,000")
    assert result.source == "model"
    assert result.used_fallback is False
    assert result.intent.intent_type == "bill_payment"
    assert result.intent.amount == 500000
    assert result.intent.target == "svc-electric"
    assert result.candidates
    assert result.candidates[0].service_id == "svc-electric"
    assert result.citations == ("svc-electric",)
    assert result.model_id == FLASH_MODEL_ID
    assert result.cost is not None and result.cost.within_ceiling


def test_resolve_intent_uses_the_pinned_prompt_and_model(catalogue):
    serving, provider = _serving(catalogue, [json_response(_intent())])
    serving.resolve_intent("pay my electricity")
    request = provider.last_request
    assert request.prompt_id == "intent_resolution"
    assert request.prompt_version == "v1"
    assert request.model_id == FLASH_MODEL_ID
    assert request.decoding.temperature == 0.0
    assert "RETRIEVED_DATA" in request.contents
    assert "pay my electricity" in request.contents


def test_resolve_intent_falls_back_when_the_provider_is_unavailable(catalogue):
    serving, _ = _serving(catalogue, [ProviderUnavailable("down")])
    result = serving.resolve_intent("pay my electricity")
    assert result.source == "fallback"
    assert result.used_fallback is True
    assert result.intent.intent_type == "unknown"
    assert result.intent.confidence == 0.0
    assert result.intent.clarifying_question is not None
    assert [item.service_id for item in result.candidates] == ["svc-electric"]


def test_resolve_intent_falls_back_on_unparseable_output(catalogue):
    serving, _ = _serving(catalogue, [text_response("not json")])
    result = serving.resolve_intent("pay my electricity")
    assert result.source == "fallback"
    assert result.intent.intent_type == "unknown"


def test_low_confidence_model_answer_is_refused(catalogue):
    serving, _ = _serving(catalogue, [json_response(_intent(confidence=0.3))])
    result = serving.resolve_intent("pay my electricity")
    assert result.intent.intent_type == "unknown"
    assert result.intent.clarifying_question is not None
    assert result.intent.clarifying_question.count("?") == 1
    assert "low_confidence" in result.flags


def test_invented_target_is_removed_before_it_reaches_the_client(catalogue):
    serving, _ = _serving(catalogue, [json_response(_intent(target="svc-ghost"))])
    result = serving.resolve_intent("pay my electricity")
    assert result.intent.target is None
    assert result.intent.intent_type == "unknown"
    assert "ungrounded_target" in result.flags


def test_untraceable_amount_is_removed(catalogue):
    serving, _ = _serving(catalogue, [json_response(_intent(amount=999999))])
    result = serving.resolve_intent("pay my electricity")
    assert result.intent.amount is None
    assert "ungrounded_amount" in result.flags


# --- MQ-002 discovery ranking ----------------------------------------------------


def _service(service_id="svc-electric", confidence=0.9):
    return {
        "service_id": service_id,
        "name": "Ikeja Electric",
        "collecting_body": "Ikeja Electricity Distribution Company",
        "category": "electricity",
        "known_amount": 1200000,
        "currency": "NGN",
        "status": "active",
        "confidence": confidence,
    }


def test_rank_services_filters_invented_results(catalogue):
    payload = {"results": [_service(), _service("svc-ghost", 0.99)], "no_match": False}
    serving, _ = _serving(catalogue, [json_response(payload)])
    outcome = serving.rank_services("electricity")
    assert outcome.source == "model"
    assert [item.service_id for item in outcome.results] == ["svc-electric"]
    assert outcome.no_match is False


def test_rank_services_reports_no_match(catalogue):
    serving, _ = _serving(catalogue, [json_response({"results": [], "no_match": True})])
    outcome = serving.rank_services("airtime topup")
    assert outcome.no_match is True
    assert outcome.results == ()


def test_rank_services_falls_back_to_keyword_search(catalogue):
    serving, _ = _serving(catalogue, [ProviderUnavailable("down")])
    outcome = serving.rank_services("electricity")
    assert outcome.source == "fallback"
    assert outcome.used_fallback is True
    assert [item.service_id for item in outcome.results] == ["svc-electric"]


# --- MQ-003 interface composition ------------------------------------------------


def test_compose_surface_returns_a_validated_stream(catalogue):
    payload = {
        "messages": [
            {"type": "createSurface", "surfaceId": "s1"},
            {
                "type": "updateComponents",
                "components": [{"component": "ConfirmationSummary", "id": "c1"}],
            },
        ]
    }
    serving, provider = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation", {"amount": 500000})
    assert outcome.source == "model"
    assert outcome.messages
    assert outcome.fallback == "confirmation"
    assert provider.last_request.prompt_id == "interface_composition"


def test_compose_surface_rejects_an_unknown_component(catalogue):
    payload = {
        "messages": [
            {
                "type": "updateComponents",
                "components": [{"component": "EvilWidget", "id": "c1"}],
            }
        ]
    }
    serving, _ = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation")
    assert outcome.used_fallback is True
    assert outcome.messages == ()
    assert outcome.fallback == "confirmation"


def test_compose_surface_rejects_a_malformed_message(catalogue):
    payload = {"messages": [{"type": "createSurface"}, "not-an-object"]}
    serving, _ = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation")
    assert outcome.used_fallback is True
    assert outcome.messages == ()


def test_compose_surface_falls_back_when_the_provider_fails(catalogue):
    serving, _ = _serving(catalogue, [ProviderUnavailable("down")])
    outcome = serving.compose_surface("receipt")
    assert outcome.used_fallback is True
    assert outcome.fallback == "receipt"


def test_unknown_task_falls_back_to_a_known_task_key(catalogue):
    serving, _ = _serving(catalogue, [ProviderUnavailable("down")])
    outcome = serving.compose_surface("mystery")
    assert outcome.fallback == "confirmation"
