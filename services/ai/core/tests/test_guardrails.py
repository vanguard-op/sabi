from __future__ import annotations

from core.grounding import build_context
from core.guardrails import (
    LANGUAGE_FALLBACK_NOTE,
    enforce_intent,
    enforce_reply,
    validate_composition,
)
from core.history import CLARIFICATION_LIMIT, CLARIFICATION_LIMIT_KEY
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


def test_low_confidence_payment_is_refused():
    intent = Intent(intent_type="bill_payment", confidence=0.4, target="svc-electric")
    outcome = enforce_intent(
        intent,
        reply="Do you mean Ikeja Electric?",
        user_text="pay light bill",
        context=_context(),
    )
    assert outcome.intent.intent_type == "unknown"
    assert outcome.intent.target == "svc-electric"
    # The model authors the follow-up in the reply; the guardrail never rewrites it.
    assert outcome.reply == "Do you mean Ikeja Electric?"
    assert "low_confidence" in outcome.flags


def test_resolved_payment_passes_unchanged():
    intent = Intent(intent_type="bill_payment", confidence=0.95, target="svc-electric")
    outcome = enforce_intent(
        intent,
        reply="I've got Ikeja Electric. Confirm and I'll prepare it.",
        user_text="pay my electricity",
        context=_context(),
    )
    assert outcome.intent.intent_type == "bill_payment"
    assert "low_confidence" not in outcome.flags


def test_ungrounded_target_forces_an_unresolved_intent():
    intent = Intent(intent_type="bill_payment", confidence=0.99, target="svc-nope")
    outcome = enforce_intent(intent, user_text="pay my bill", context=_context())
    assert outcome.intent.intent_type == "unknown"
    assert outcome.intent.target is None
    assert "ungrounded_target" in outcome.flags


def test_unsupported_language_is_flagged_and_noted_but_reply_is_not_edited():
    intent = Intent(
        intent_type="discovery",
        confidence=0.95,
        detected_language="ha",
    )
    reply = "I found some options for you."
    outcome = enforce_intent(intent, reply=reply, user_text="ina son sayi", context=_context())
    assert outcome.language_fallback is True
    assert outcome.note == LANGUAGE_FALLBACK_NOTE
    assert "unsupported_language" in outcome.flags
    # The reply wording is the model's and is never post-processed.
    assert outcome.reply == reply


def test_supported_language_does_not_fall_back():
    intent = Intent(
        intent_type="discovery",
        confidence=0.95,
        detected_language="pcm",
    )
    outcome = enforce_intent(intent, user_text="i wan buy light", context=_context())
    assert outcome.language_fallback is False
    assert outcome.note is None


# --- Reply boundaries (MQ-001) ----------------------------------------------------


def test_reply_with_executable_code_is_dropped():
    reply = "Sure: <script>alert('x')</script>"
    safe, flags = enforce_reply(reply, context=_context())
    assert safe is None
    assert "unsafe_reply" in flags


def test_reply_with_a_url_is_dropped():
    safe, flags = enforce_reply("Pay here: https://example.com/pay", context=_context())
    assert safe is None
    assert "unsafe_reply" in flags


def test_reply_with_an_ungrounded_amount_is_dropped():
    # No amount is in the context and none was stated by the user.
    safe, flags = enforce_reply("Your bill is ₦9,999.", context=_context())
    assert safe is None
    assert "ungrounded_reply" in flags


def test_reply_stating_a_grounded_amount_is_kept():
    record = RetrievedRecord.from_service(
        {
            "service_id": "svc-electric",
            "name": "Ikeja Electric",
            "collecting_body": "Ikeja Electricity Distribution Company",
            "category": "electricity",
            "currency": "NGN",
            "known_amount": 500000,
        }
    )
    context = build_context([record])
    safe, flags = enforce_reply("The known amount is ₦5,000.", context=context)
    assert safe == "The known amount is ₦5,000."
    assert flags == frozenset()


def test_reply_restating_the_users_own_amount_is_kept():
    # The user stated the amount; confirming it back is grounded, not an invention.
    safe, flags = enforce_reply(
        "Sure — ₦5,000 for Ikeja Electric. Confirm and I'll prepare it.",
        context=_context(),
        user_text="pay 5000 for electricity",
    )
    assert safe is not None
    assert flags == frozenset()


def test_reply_with_an_ungrounded_service_identifier_is_dropped():
    safe, flags = enforce_reply("I found svc-ghost for you.", context=_context())
    assert safe is None
    assert "ungrounded_reply" in flags


def test_plain_reply_passes_without_edits():
    reply = "Hi — I can help you pay levies and bills. What would you like to pay?"
    safe, flags = enforce_reply(reply, context=_context())
    assert safe == reply
    assert flags == frozenset()


def test_missing_or_empty_reply_is_null_not_a_crash():
    assert enforce_reply(None, context=_context()) == (None, frozenset())
    safe, flags = enforce_reply("   ", context=_context())
    assert safe is None
    assert "empty_reply" in flags


# --- Non-command (MQ-001) ---------------------------------------------------------


def test_non_command_sets_no_payment_field():
    intent = Intent(
        intent_type="non_command",
        confidence=1.0,
        target="svc-electric",
        amount=500000,
        reference="REF-1",
    )
    outcome = enforce_intent(
        intent,
        reply="I can help you pay levies and bills.",
        user_text="hello",
        context=_context(),
    )
    assert outcome.intent.intent_type == "non_command"
    assert outcome.intent.target is None
    assert outcome.intent.amount is None
    assert outcome.intent.reference is None
    assert outcome.reply == "I can help you pay levies and bills."
    assert "non_command" in outcome.flags
    assert "low_confidence" not in outcome.flags


# --- The three-question bound (MQ-001) --------------------------------------------


def test_still_asks_below_the_clarification_bound():
    intent = Intent(intent_type="bill_payment", confidence=0.3, target=None)
    outcome = enforce_intent(
        intent,
        reply="Which biller do you mean?",
        user_text="pay something",
        context=_context(),
        clarifications_asked=CLARIFICATION_LIMIT - 1,
    )
    assert outcome.intent.intent_type == "unknown"
    assert outcome.reply == "Which biller do you mean?"
    assert "clarification_limit_reached" not in outcome.flags


def test_declines_at_the_clarification_bound():
    intent = Intent(intent_type="bill_payment", confidence=0.3, target=None)
    outcome = enforce_intent(
        intent,
        reply="Three answers in and I still can't tell which one you mean.",
        user_text="pay something",
        context=_context(),
        clarifications_asked=CLARIFICATION_LIMIT,
    )
    assert outcome.intent.intent_type == "unknown"
    assert outcome.intent.constraints.get(CLARIFICATION_LIMIT_KEY) is True
    assert "clarification_limit_reached" in outcome.flags
    # The after-bound reply is the model's; the structured contract asks no question.
    assert outcome.reply is not None


# --- Composition ------------------------------------------------------------------


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
