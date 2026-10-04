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
    service, _ = _service(catalogue, [json_response(_intent(confidence=0.2))])
    outcome = service.resolve("pay my electricity")
    assert "low_confidence" in outcome.flags
    assert outcome.response.intent.intentType == "unknown"
    assert outcome.response.intent.clarifyingQuestion is not None


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
    assert outcome.response.intent.clarifyingQuestion is None


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
    assert outcome.response.intent.clarifyingQuestion is None
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
