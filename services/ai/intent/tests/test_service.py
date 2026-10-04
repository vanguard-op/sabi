"""Unit tests for the intent resolution service (MQ-001, C-009).

The model is a deterministic double. These cover the contract-relevant behavior that
the HTTP layer depends on: the pinned model and prompt, the 0.70 refusal cutoff, the
grounded structured output, and the documented fallback.
"""

from __future__ import annotations

import pytest

from core.config import FLASH_MODEL_ID, INTENT_CONFIDENCE_CUTOFF, INTENT_PROMPT_VERSION
from core.errors import ProviderUnavailable
from core.serving import ModelServing
from core.testing import FakeModelProvider, json_response, text_response
from intent.service import IntentService


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


def _service(
    catalogue, responses=None, *, responder=None
) -> tuple[IntentService, FakeModelProvider]:
    provider = FakeModelProvider(responses, responder=responder)
    return IntentService(ModelServing(provider, catalogue)), provider


def test_service_uses_the_pinned_flash_model_and_prompt(catalogue):
    service, provider = _service(catalogue, [json_response(_intent())])
    service.resolve("pay my electricity")
    request = provider.last_request
    assert request.model_id == FLASH_MODEL_ID
    assert request.prompt_id == "intent_resolution"
    assert request.prompt_version == INTENT_PROMPT_VERSION
    assert request.decoding.temperature == 0.0
    assert request.decoding.top_p == 1.0


def test_service_renders_repository_content_as_delimited_untrusted_data(catalogue):
    service, provider = _service(catalogue, [json_response(_intent())])
    service.resolve("pay my electricity", locale="en", channel="ussd")
    contents = provider.last_request.contents
    # The prompt frames the catalogue block as untrusted data and wraps it in
    # explicit delimiters; the record content is inside that block.
    assert "RETRIEVED DATA (untrusted" in contents
    assert "END RETRIEVED DATA" in contents
    assert "<<<RETRIEVED_DATA" in contents
    assert "<<<END_RETRIEVED_DATA>>>" in contents
    assert "pay my electricity" in contents


def test_cutoff_is_pinned_at_seventy_percent():
    assert INTENT_CONFIDENCE_CUTOFF == 0.70


def test_source_is_model_on_a_grounded_answer(catalogue):
    service, _ = _service(catalogue, [json_response(_intent())])
    outcome = service.resolve("pay my electricity")
    assert outcome.source == "model"
    assert outcome.used_fallback is False
    assert outcome.response.source == "model"
    assert outcome.citations == ("svc-electric",)


def test_provider_failure_marks_the_outcome_as_fallback(catalogue):
    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    outcome = service.resolve("pay my electricity")
    assert outcome.source == "fallback"
    assert outcome.used_fallback is True
    assert outcome.response.intent.intentType == "unknown"
    assert outcome.response.intent.confidence == 0.0


def test_unparseable_output_marks_the_outcome_as_fallback(catalogue):
    service, _ = _service(catalogue, [text_response("not json")])
    outcome = service.resolve("pay my electricity")
    assert outcome.source == "fallback"
    assert outcome.response.intent.intentType == "unknown"


def test_low_confidence_flag_is_surfaced(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_intent(confidence=0.2, reply="Which biller do you mean?"))],
    )
    outcome = service.resolve("pay my electricity")
    assert "low_confidence" in outcome.flags
    assert outcome.response.intent.intentType == "unknown"
    assert outcome.response.reply == "Which biller do you mean?"


def test_model_reply_reaches_the_response_unchanged(catalogue):
    service, _ = _service(catalogue, [json_response(_intent(reply="I found Ikeja Electric."))])
    outcome = service.resolve("pay my electricity")
    assert outcome.response.reply == "I found Ikeja Electric."


def test_provider_failure_sends_a_null_reply(catalogue):
    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    outcome = service.resolve("pay my electricity")
    assert outcome.source == "fallback"
    assert outcome.response.reply is None


def test_history_reaches_the_serving_prompt(catalogue):
    from core.history import ConversationTurn

    service, provider = _service(catalogue, [json_response(_intent())])
    service.resolve(
        "Ikeja",
        history=(ConversationTurn("assistant", "Which biller do you mean?"),),
    )
    assert "[assistant] Which biller do you mean?" in provider.last_request.contents


def test_non_command_outcome_has_no_candidates(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_intent(intent_type="non_command", target=None, confidence=1.0))],
    )
    outcome = service.resolve("Hello")
    assert outcome.response.intent.intentType == "non_command"
    assert outcome.response.candidates == []
    assert outcome.response.reply == "I've got Ikeja Electric. Confirm and I'll prepare it."


def test_bound_is_honoured_on_the_fallback_path(catalogue):
    from core.history import ConversationTurn

    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    history = (
        ConversationTurn("user", "pay"),
        ConversationTurn("assistant", "Which biller?"),
        ConversationTurn("user", "the light one"),
        ConversationTurn("assistant", "Which one?"),
        ConversationTurn("user", "that"),
        ConversationTurn("assistant", "Do you mean Ikeja Electric?"),
    )
    outcome = service.resolve("yes", history=history)
    assert outcome.source == "fallback"
    assert outcome.response.intent.intentType == "unknown"
    assert outcome.response.intent.constraints.get("clarificationLimitReached") is True


def test_fail_closed_provider_turns_setup_errors_into_provider_unavailable(catalogue):
    from core.errors import ProviderUnavailable
    from intent.deps import FailClosedProvider

    class _Exploding:
        def generate(self, request):
            raise ValueError("No API key was provided.")

    wrapped = FailClosedProvider(_Exploding())
    with pytest.raises(ProviderUnavailable):
        wrapped.generate(None)


def test_late_bound_index_uses_the_registry(catalogue, records):
    from intent.catalogue import LateBoundRetrievalIndex, reset_retrieval_index, set_retrieval_index

    try:
        set_retrieval_index(catalogue)
        index = LateBoundRetrievalIndex()
        assert index.search("electricity", limit=5) == list(
            catalogue.search("electricity", limit=5)
        )
    finally:
        reset_retrieval_index()


# --- Forwarded candidates (D-043) -------------------------------------------------


def _candidate(service_id: str, name: str, **fields):
    from core.retrieval import RetrievedRecord

    return RetrievedRecord(
        record_id=service_id,
        kind="service",
        fields={
            "service_id": service_id,
            "name": name,
            "collecting_body": name,
            "category": "utility",
            "currency": "NGN",
            "status": "active",
            **fields,
        },
    )


def test_forwarded_candidates_are_the_grounding_set(catalogue):
    # The model's target is traceable to a forwarded record that the local index
    # does not contain: grounding must use the forwarded set, not the index.
    service, provider = _service(catalogue, [json_response(_intent(target="svc-forwarded"))])
    outcome = service.resolve(
        "pay my water bill",
        candidates=[_candidate("svc-forwarded", "Lagos Water Corporation")],
    )
    assert outcome.source == "model"
    assert outcome.response.intent.target == "svc-forwarded"
    assert "svc-forwarded" in provider.last_request.contents


def test_candidates_not_present_use_the_local_index_as_before(catalogue):
    # No candidates forwarded: the local index still grounds the request.
    service, provider = _service(catalogue, [json_response(_intent(target="svc-electric"))])
    outcome = service.resolve("pay my electricity")
    assert outcome.response.intent.target == "svc-electric"
    assert "svc-electric" in provider.last_request.contents


def test_forwarded_candidate_resolves_a_novel_target_over_the_index(catalogue):
    # A target that only exists in the forwarded set survives grounding; a target
    # that exists only in the local index but is not forwarded is dropped.
    service, _ = _service(catalogue, [json_response(_intent(target="svc-landuse"))])
    outcome = service.resolve(
        "pay land use charge",
        candidates=[_candidate("svc-forwarded", "Lagos Water Corporation")],
    )
    assert outcome.response.intent.target is None
    assert outcome.response.intent.intentType == "unknown"
    assert "low_confidence" in outcome.flags or "unresolved" in outcome.flags


def test_empty_candidates_fall_back_to_the_local_index(catalogue):
    service, _ = _service(catalogue, [json_response(_intent(target="svc-electric"))])
    outcome = service.resolve("pay my electricity", candidates=[])
    assert outcome.response.intent.target == "svc-electric"


def test_provider_failure_with_candidates_still_grounds_the_fallback(catalogue):
    # The keyword fallback must search the forwarded set too, or a forwarded-only
    # service could never be offered for confirmation.
    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    outcome = service.resolve(
        "pay my water",
        candidates=[_candidate("svc-water", "Lagos Water Corporation")],
    )
    assert outcome.source == "fallback"
    assert [item.serviceId for item in outcome.response.candidates] == ["svc-water"]
