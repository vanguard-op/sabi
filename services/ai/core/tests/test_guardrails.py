from __future__ import annotations

from core.grounding import build_context
from core.guardrails import (
    DEFAULT_CLARIFYING_QUESTION,
    LANGUAGE_FALLBACK_NOTE,
    enforce_intent,
    normalize_question,
    validate_composition,
)
from core.retrieval import RetrievedRecord
from core.schemas import CLIENT_COMPONENT_CATALOGUE, Intent


def _context():
    record = RetrievedRecord.from_service(
        {
            "service_id": "svc-electric",
            "name": "Ikeja Electric",
            "collecting_body": "Ikeja Electricity Distribution Company",
            "category": "electricity",
            "currency": "NGN",
        }
    )
    return build_context([record])


def test_low_confidence_payment_is_refused_and_asks_one_question():
    intent = Intent(
        intent_type="bill_payment",
        confidence=0.4,
        target="svc-electric",
        clarifying_question="Do you mean Ikeja Electric? Is that right?",
    )
    outcome = enforce_intent(intent, user_text="pay light bill", context=_context())
    assert outcome.intent.intent_type == "unknown"
    assert outcome.intent.clarifying_question == "Do you mean Ikeja Electric?"
    assert "low_confidence" in outcome.flags


def test_resolved_payment_passes_unchanged():
    intent = Intent(intent_type="bill_payment", confidence=0.95, target="svc-electric")
    outcome = enforce_intent(intent, user_text="pay my electricity", context=_context())
    assert outcome.intent.intent_type == "bill_payment"
    assert outcome.intent.clarifying_question is None
    assert "low_confidence" not in outcome.flags


def test_ungrounded_target_forces_a_clarifying_question():
    intent = Intent(intent_type="bill_payment", confidence=0.99, target="svc-nope")
    outcome = enforce_intent(intent, user_text="pay my bill", context=_context())
    assert outcome.intent.intent_type == "unknown"
    assert outcome.intent.target is None
    assert outcome.intent.clarifying_question is not None
    assert "ungrounded_target" in outcome.flags


def test_normalize_question_keeps_exactly_one():
    assert normalize_question("A? B? C?") == "A?"
    assert normalize_question("No question mark here") == "No question mark here?"
    assert normalize_question("") == DEFAULT_CLARIFYING_QUESTION
    assert normalize_question(None) == DEFAULT_CLARIFYING_QUESTION


def test_unsupported_language_falls_back_to_english_with_a_note():
    intent = Intent(
        intent_type="discovery",
        confidence=0.95,
        language="ha",
        detected_language="ha",
    )
    outcome = enforce_intent(intent, user_text="ina son sayi", context=_context())
    assert outcome.language_fallback is True
    assert outcome.note == LANGUAGE_FALLBACK_NOTE
    assert "unsupported_language" in outcome.flags


def test_supported_language_does_not_fall_back():
    intent = Intent(
        intent_type="discovery",
        confidence=0.95,
        language="pcm",
        detected_language="pcm",
    )
    outcome = enforce_intent(intent, user_text="i wan buy light", context=_context())
    assert outcome.language_fallback is False
    assert outcome.note is None


def _message(component: str):
    return {
        "type": "updateComponents",
        "components": [{"component": component, "id": "c1"}],
    }


def test_valid_composition_passes():
    validation = validate_composition(
        [
            {"type": "createSurface", "surfaceId": "s1"},
            _message("ConfirmationSummary"),
        ],
        allowed_components=CLIENT_COMPONENT_CATALOGUE,
    )
    assert validation.ok is True
    assert "ConfirmationSummary" in validation.component_names


def test_unknown_component_is_rejected():
    validation = validate_composition(
        [_message("EvilWidget")],
        allowed_components=CLIENT_COMPONENT_CATALOGUE,
    )
    assert validation.ok is False
    assert any("unknown component" in error for error in validation.errors)


def test_executable_content_is_rejected():
    validation = validate_composition(
        [{"type": "updateDataModel", "data": "<script>alert(1)</script>"}],
        allowed_components=CLIENT_COMPONENT_CATALOGUE,
    )
    assert validation.ok is False


def test_external_resource_load_is_rejected():
    validation = validate_composition(
        [{"type": "updateDataModel", "data": "https://evil.example/x.js"}],
        allowed_components=CLIENT_COMPONENT_CATALOGUE,
    )
    assert validation.ok is False


def test_unknown_message_type_is_rejected():
    validation = validate_composition(
        [{"type": "runPayment"}],
        allowed_components=CLIENT_COMPONENT_CATALOGUE,
    )
    assert validation.ok is False
