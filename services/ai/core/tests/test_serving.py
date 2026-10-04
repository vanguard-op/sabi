from __future__ import annotations

import pytest

from core.config import FLASH_MODEL_ID, INTENT_PROMPT_VERSION
from core.errors import ProviderUnavailable
from core.history import ConversationTurn
from core.serving import ModelServing
from core.testing import FakeModelProvider, json_response, text_response


def _serving(catalogue, responses=None, *, responder=None):
    provider = FakeModelProvider(responses, responder=responder)
    return ModelServing(provider, catalogue), provider


def _intent(**overrides):
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
    # The model authors the user-facing reply; it is passed through, not pinned.
    assert result.reply == "I've got Ikeja Electric. Confirm and I'll prepare it."


def test_resolve_intent_uses_the_pinned_prompt_and_model(catalogue):
    serving, provider = _serving(catalogue, [json_response(_intent())])
    serving.resolve_intent("pay my electricity")
    request = provider.last_request
    assert request.prompt_id == "intent_resolution"
    assert request.prompt_version == INTENT_PROMPT_VERSION
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
    # The degraded path sends no reply: the client renders its prewritten fallback.
    assert result.reply is None
    assert [item.service_id for item in result.candidates] == ["svc-electric"]


def test_resolve_intent_falls_back_on_unparseable_output(catalogue):
    serving, _ = _serving(catalogue, [text_response("not json")])
    result = serving.resolve_intent("pay my electricity")
    assert result.source == "fallback"
    assert result.intent.intent_type == "unknown"


def test_low_confidence_model_answer_is_refused(catalogue):
    serving, _ = _serving(
        catalogue,
        [json_response(_intent(confidence=0.3, reply="Which biller do you mean?"))],
    )
    result = serving.resolve_intent("pay my electricity")
    assert result.intent.intent_type == "unknown"
    assert result.reply == "Which biller do you mean?"
    assert "low_confidence" in result.flags


def test_unsafe_reply_is_dropped_to_null(catalogue):
    serving, _ = _serving(
        catalogue,
        [json_response(_intent(reply="Pay at https://example.com/pay"))],
    )
    result = serving.resolve_intent("pay my electricity")
    assert result.source == "model"
    assert result.reply is None
    assert "unsafe_reply" in result.flags


def test_missing_reply_does_not_crash(catalogue):
    serving, _ = _serving(catalogue, [json_response(_intent(reply=None))])
    result = serving.resolve_intent("pay my electricity")
    assert result.source == "model"
    assert result.reply is None


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


# --- MQ-001 multi-turn history and the clarification bound ------------------------


def test_history_is_rendered_into_the_prompt(catalogue):
    serving, provider = _serving(catalogue, [json_response(_intent())])
    history = (
        ConversationTurn("user", "I wan pay something"),
        ConversationTurn("assistant", "Which biller do you mean?"),
    )
    serving.resolve_intent("Ikeja", history=history)
    contents = provider.last_request.contents
    assert "[user] I wan pay something" in contents
    assert "[assistant] Which biller do you mean?" in contents
    assert "1" in contents  # clarifying questions already asked


def test_non_command_has_no_candidates_or_payment_fields(catalogue):
    serving, _ = _serving(
        catalogue,
        [
            json_response(
                _intent(
                    intent_type="non_command",
                    target=None,
                    confidence=1.0,
                    reply="I can help you pay levies and bills.",
                )
            )
        ],
    )
    result = serving.resolve_intent("Hello")
    assert result.intent.intent_type == "non_command"
    assert result.intent.target is None
    assert result.reply == "I can help you pay levies and bills."
    assert result.candidates == ()


def test_third_clarification_turn_declines(catalogue):
    serving, _ = _serving(
        catalogue,
        [json_response(_intent(confidence=0.2, reply="Three answers in and I still can't tell."))],
    )
    history = (
        ConversationTurn("user", "pay something"),
        ConversationTurn("assistant", "Which biller?"),
        ConversationTurn("user", "the light one"),
        ConversationTurn("assistant", "Which of these two?"),
        ConversationTurn("user", "that one"),
        ConversationTurn("assistant", "Do you mean Ikeja Electric?"),
    )
    result = serving.resolve_intent("yes", history=history)
    assert result.intent.intent_type == "unknown"
    assert result.intent.constraints.get("clarificationLimitReached") is True
    assert "clarification_limit_reached" in result.flags


def test_second_clarification_turn_still_asks(catalogue):
    serving, _ = _serving(
        catalogue, [json_response(_intent(confidence=0.2, reply="Which biller do you mean?"))]
    )
    history = (
        ConversationTurn("user", "pay something"),
        ConversationTurn("assistant", "Which biller?"),
    )
    result = serving.resolve_intent("the light one", history=history)
    assert result.intent.intent_type == "unknown"
    assert result.reply == "Which biller do you mean?"
    assert "clarification_limit_reached" not in result.flags


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

_CATALOG_ID = "https://sabi.app/a2ui/v1/catalog.json"


def _stream(*components, surface_id="s1"):
    return {
        "messages": [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": surface_id, "catalogId": _CATALOG_ID},
            },
            {
                "version": "v0.9",
                "updateComponents": {"surfaceId": surface_id, "components": list(components)},
            },
        ]
    }


def test_compose_surface_returns_a_validated_stream(catalogue):
    payload = _stream(
        {"id": "root", "component": "ConfirmationSummary", "amount": 500000, "payee": "Ikeja"},
    )
    serving, provider = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation", {"amount": 500000}, catalog_id=_CATALOG_ID)
    assert outcome.source == "model"
    assert outcome.messages
    assert outcome.fallback == "confirmation"
    assert outcome.catalog_id == _CATALOG_ID
    assert provider.last_request.prompt_id == "interface_composition"
    assert _CATALOG_ID in provider.last_request.contents


@pytest.mark.parametrize("task", ["verification", "recovery"])
def test_compose_surface_accepts_the_new_tasks(catalogue, task):
    component = "Verification" if task == "verification" else "Recovery"
    payload = _stream({"id": "root", "component": component, "title": "Verify"})
    serving, provider = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface(task, {"state": "pending"}, catalog_id=_CATALOG_ID)
    assert outcome.source == "model"
    assert outcome.fallback == task
    assert task in provider.last_request.contents


def test_compose_surface_receipt_carries_a_resolved_record(catalogue):
    payload = _stream(
        {
            "id": "root",
            "component": "ReceiptCard",
            "reference": "FT-1",
            "payee": "Agency",
            "amount": 100,
        },
    )
    serving, provider = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface(
        "receipt", {"reference": "FT-1", "receiptId": "rcpt-1"}, catalog_id=_CATALOG_ID
    )
    assert outcome.source == "model"
    assert outcome.fallback == "receipt"
    assert "FT-1" in provider.last_request.contents


def test_compose_surface_rejects_an_unknown_component(catalogue):
    payload = _stream({"id": "root", "component": "EvilWidget", "x": 1})
    serving, _ = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation", catalog_id=_CATALOG_ID)
    assert outcome.used_fallback is True
    assert outcome.messages == ()
    assert outcome.fallback == "confirmation"


def test_compose_surface_rejects_a_surface_naming_another_catalog(catalogue):
    payload = {
        "messages": [
            {
                "version": "v0.9",
                "createSurface": {"surfaceId": "s1", "catalogId": "https://other/x.json"},
            },
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s1",
                    "components": [
                        {
                            "id": "root",
                            "component": "ConfirmationSummary",
                            "amount": 1,
                            "payee": "x",
                        }
                    ],
                },
            },
        ]
    }
    serving, _ = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation", catalog_id=_CATALOG_ID)
    assert outcome.used_fallback is True
    assert outcome.messages == ()


def test_compose_surface_rejects_a_missing_required_property(catalogue):
    payload = _stream({"id": "root", "component": "ConfirmationSummary", "amount": 500000})
    serving, _ = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation", catalog_id=_CATALOG_ID)
    assert outcome.used_fallback is True
    assert outcome.messages == ()


def test_compose_surface_rejects_a_malformed_message(catalogue):
    payload = {
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": "s1"}},
            "not-an-object",
        ]
    }
    serving, _ = _serving(catalogue, [json_response(payload, model_id="primary")])
    outcome = serving.compose_surface("confirmation", catalog_id=_CATALOG_ID)
    assert outcome.used_fallback is True
    assert outcome.messages == ()


def test_compose_surface_falls_back_when_the_provider_fails(catalogue):
    serving, _ = _serving(catalogue, [ProviderUnavailable("down")])
    outcome = serving.compose_surface("receipt", catalog_id=_CATALOG_ID)
    assert outcome.used_fallback is True
    assert outcome.fallback == "receipt"


def test_compose_surface_falls_back_without_a_compatible_catalog(catalogue):
    # An absent or unknown catalog degrades to the same-task fallback, never a
    # failure (C-012 revision 2; FEAT-011 edge case).
    serving, provider = _serving(catalogue, [])
    for catalog_id in (None, "", "https://nope.example/catalog.json"):
        outcome = serving.compose_surface("discovery", catalog_id=catalog_id)
        assert outcome.used_fallback is True
        assert outcome.messages == ()
        assert outcome.fallback == "discovery"
        assert outcome.catalog_id is None
    assert provider.requests == []


def test_unknown_task_falls_back_to_a_known_task_key(catalogue):
    serving, _ = _serving(catalogue, [ProviderUnavailable("down")])
    outcome = serving.compose_surface("mystery", catalog_id=_CATALOG_ID)
    assert outcome.fallback == "confirmation"


def test_composition_validates_against_the_injected_catalog(catalogue):
    """The serving seam composes against whichever catalog it was built with.

    A custom catalog with one component of its own proves the agent is not
    validating against a fixed private name list: a component that is catalog-
    defined passes, and the published name is refused.
    """
    from core.a2ui_catalog import A2uiCatalog

    custom = A2uiCatalog(
        catalog_id="https://example.test/a2ui/v1/catalog.json",
        components={
            "CustomCard": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            }
        },
    )
    provider = FakeModelProvider(
        [
            json_response(
                {
                    "messages": [
                        {
                            "version": "v0.9",
                            "createSurface": {
                                "surfaceId": "s1",
                                "catalogId": custom.catalog_id,
                            },
                        },
                        {
                            "version": "v0.9",
                            "updateComponents": {
                                "surfaceId": "s1",
                                "components": [
                                    {"id": "root", "component": "CustomCard", "title": "Hi"}
                                ],
                            },
                        },
                    ]
                },
                model_id="primary",
            )
        ]
    )
    serving = ModelServing(provider, catalogue, catalog=custom)
    outcome = serving.compose_surface("confirmation", catalog_id=custom.catalog_id)
    assert outcome.source == "model"
    assert outcome.catalog_id == custom.catalog_id
