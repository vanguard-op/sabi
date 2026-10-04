from __future__ import annotations

import pytest

from core.config import Capability, prompt_version_for
from core.errors import ModelError
from core.prompts import load_prompt, render


@pytest.mark.parametrize("capability", list(Capability))
def test_every_capability_has_a_versioned_prompt(capability):
    prompt = load_prompt(capability)
    assert prompt.version == prompt_version_for(capability)
    assert prompt.prompt_id == capability.value
    assert len(prompt.sha256) == 64
    assert prompt.text.strip()


def test_prompt_is_content_hashed_and_stable():
    first = load_prompt(Capability.INTENT_RESOLUTION)
    second = load_prompt(Capability.INTENT_RESOLUTION)
    assert first.sha256 == second.sha256


def test_unknown_prompt_version_is_rejected():
    with pytest.raises(ModelError):
        load_prompt(Capability.INTENT_RESOLUTION, "v99")
    with pytest.raises(ModelError):
        load_prompt(Capability.INTENT_RESOLUTION, "not-a-version")


def test_render_substitutes_tokens_and_keeps_unknown_ones():
    template = "hello [[name]] and [[missing]]"
    assert render(template, {"name": "world"}) == "hello world and [[missing]]"


def test_intent_prompt_carries_grounding_and_refusal_rules():
    text = load_prompt(Capability.INTENT_RESOLUTION).text
    assert "Never invent" in text
    assert "exactly one clarifying question" in text
    assert "RETRIEVED DATA" in text
    assert "untrusted" in text.lower()


def test_intent_prompt_asks_for_the_reply_and_binds_the_locale():
    text = load_prompt(Capability.INTENT_RESOLUTION).text
    # The model authors the user-facing message; the locale is an instruction to reply
    # in that language, not a fixed client string.
    assert "reply" in text
    assert "[[locale]]" in text
    assert 'Write the "reply" in that language' in text
    # The reply boundaries the guardrails enforce are stated to the model.
    assert "no URLs" in text or "no code and no URLs" in text
    assert "another user's data" in text


def test_intent_prompt_carries_the_conversation_rules():
    from core.config import INTENT_PROMPT_VERSION

    prompt = load_prompt(Capability.INTENT_RESOLUTION)
    assert prompt.version == INTENT_PROMPT_VERSION
    text = prompt.text
    # Multi-turn context, non-command classification, and the three-question bound.
    assert "[[conversation_history]]" in text
    assert "non_command" in text
    assert "[[clarification_limit]]" in text
    assert "At most [[clarification_limit]]" in text


def test_intent_prompt_states_the_pinned_cutoff():
    from core.config import INTENT_CONFIDENCE_CUTOFF

    text = load_prompt(Capability.INTENT_RESOLUTION).text
    assert str(INTENT_CONFIDENCE_CUTOFF) in text
    assert "0.80" not in text


def test_intent_prompt_v4_carries_the_conversational_instruction_and_few_shots():
    from core.config import INTENT_PROMPT_VERSION

    prompt = load_prompt(Capability.INTENT_RESOLUTION)
    assert prompt.version == INTENT_PROMPT_VERSION == "v4"
    text = prompt.text
    # The template keeps the token mechanism and the untrusted-data delimiters and
    # security rules.
    assert "[[user_message]]" in text
    assert "[[retrieved_data]]" in text
    assert "[[conversation_history]]" in text
    assert "[[locale]]" in text
    assert "END RETRIEVED DATA" in text
    assert "untrusted" in text.lower()
    # The conversational reply, explicit failure behavior, the exact output contract,
    # reasoning guidance, and the few-shot examples the capability requires.
    assert "EXAMPLES" in text
    assert "HOW TO DECIDE" in text
    assert "THE REPLY" in text
    assert "non_command" in text
    assert "unknown" in text
    assert "OUTPUT" in text


def test_intent_prompt_v4_keeps_the_pinned_cutoff_and_example_shapes():
    from core.config import INTENT_CONFIDENCE_CUTOFF

    text = load_prompt(Capability.INTENT_RESOLUTION).text
    assert str(INTENT_CONFIDENCE_CUTOFF) in text
    # The four required example shapes are present.
    assert "greeting" in text.lower()
    assert "Pidgin" in text
    assert "follow-up" in text.lower()
    assert "unmappable" in text.lower()


def test_composition_prompt_v3_carries_the_a2ui_catalog_contract():
    from core.config import INTERFACE_COMPOSITION_PROMPT_VERSION

    prompt = load_prompt(Capability.INTERFACE_COMPOSITION)
    assert prompt.version == INTERFACE_COMPOSITION_PROMPT_VERSION == "v3"
    text = prompt.text
    # The composed surface is an A2UI v0.9 message stream against the published
    # catalog: the negotiated catalogId and its components are rendered in, and the
    # template keeps the token mechanism and the security rules (FEAT-011, MQ-003).
    assert "[[catalog_id]]" in text
    assert "[[catalog_components]]" in text
    assert "[[task]]" in text
    assert "[[context]]" in text
    assert "v0.9" in text
    assert "createSurface" in text
    assert "updateComponents" in text
    assert "updateDataModel" in text
    assert "root" in text
    assert "verification" in text
    assert "recovery" in text
    assert "untrusted" in text.lower()
    assert "Never request a" in text
    assert "outside the catalog" in text
    assert "record lookup" in text
    assert "prewritten" in text.lower()
