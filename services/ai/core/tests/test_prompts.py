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


def test_composition_prompt_forbids_executable_content():
    text = load_prompt(Capability.INTERFACE_COMPOSITION).text
    assert "executable code" in text
    assert "external resource loads" in text
