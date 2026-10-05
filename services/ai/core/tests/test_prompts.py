from __future__ import annotations

import re

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


def test_composition_prompt_v4_carries_the_a2ui_catalog_contract():
    from core.config import INTERFACE_COMPOSITION_PROMPT_VERSION

    prompt = load_prompt(Capability.INTERFACE_COMPOSITION)
    assert prompt.version == INTERFACE_COMPOSITION_PROMPT_VERSION == "v4"
    text = prompt.text
    # The composed surface is an A2UI v0.9 message stream against the published
    # catalog: the negotiated catalogId and its components are rendered in, and the
    # template keeps the token mechanism and the security rules (FEAT-011, MQ-003).
    assert "[[catalog_id]]" in text
    assert "[[allowed_components]]" in text
    assert "[[task]]" in text
    assert "[[context]]" in text
    assert "[[task_context_fields]]" in text
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
    # The required-property rule is satisfiable: the prompt states the per-task
    # required context and scopes the empty-stream escape hatch to a task the catalog
    # genuinely cannot represent, so it never demands a property the context lacks.
    assert "REQUIRED CONTEXT PER TASK" in text
    assert "the caller supplies and what the context carries" in text
    assert "Do not return an" in text and "empty list when CONTEXT carries" in text
    assert "every message must pass" not in text.lower()


def test_composition_prompt_states_the_shared_per_task_fields():
    """The prompt's per-task fields are the same contract the serving guard uses."""

    from core.config import INTERFACE_COMPOSITION_PROMPT_VERSION
    from core.schemas import TASK_CONTEXT_FIELDS

    prompt = load_prompt(Capability.INTERFACE_COMPOSITION)
    rendered = render(prompt.text, _render_values(Capability.INTERFACE_COMPOSITION, _catalog()))
    assert prompt.version == INTERFACE_COMPOSITION_PROMPT_VERSION
    for task, fields in TASK_CONTEXT_FIELDS.items():
        assert f"- {task}: " in rendered
        for field in fields:
            assert field in rendered


# --- Rendered-prompt integrity ----------------------------------------------------
# Every placeholder a capability prompt declares must be supplied by the serving
# layer, or the model silently receives the literal token. Mocked model tests cannot
# catch this: they assert on the request object, not on whether a token rendered, so
# a prompt/code key mismatch degrades every surface to the fallback while the suite
# stays green. These render each prompt with the exact substitution map ``serving``
# builds and assert the result is clean and grounded (FEAT-011, MQ-003).

_PLACEHOLDER_RE = re.compile(r"\[\[[a-z_]+\]\]")


def _catalog():
    from core.a2ui_catalog import published_catalog

    return published_catalog()


def _render_values(capability, catalog):
    """The values ``serving`` supplies for each capability, built the same way.

    Kept in lockstep with ``core.serving``: a placeholder the prompt declares and
    this map omits renders as a literal token and fails the assertions below, which
    is the regression the composition token caused.
    """

    if capability is Capability.INTENT_RESOLUTION:
        return {
            "user_message": "pay my electricity",
            "locale": "en",
            "channel": "app",
            "retrieved_data": "RETRIEVED DATA\n[]\nEND RETRIEVED DATA",
            "conversation_history": "",
            "clarifying_questions_asked": "0",
            "clarification_limit": "3",
        }
    if capability is Capability.DISCOVERY_RANKING:
        return {
            "user_query": "electricity",
            "category": "none",
            "retrieved_data": "RETRIEVED DATA\n[]\nEND RETRIEVED DATA",
        }
    if capability is Capability.INTERFACE_COMPOSITION:
        from core.schemas import render_task_context_fields

        return {
            "catalog_id": catalog.catalog_id,
            "task": "confirmation",
            "context": "{}",
            "allowed_components": ", ".join(catalog.component_names()),
            "task_context_fields": render_task_context_fields(),
        }
    raise AssertionError(f"no render map for {capability}")


@pytest.mark.parametrize("capability", list(Capability))
def test_every_capability_prompt_renders_without_leftover_placeholders(capability):
    from core.a2ui_catalog import published_catalog

    prompt = load_prompt(capability)
    rendered = render(prompt.text, _render_values(capability, published_catalog()))
    leftover = _PLACEHOLDER_RE.findall(rendered)
    assert leftover == [], f"{capability.value} renders unresolved placeholders: {leftover}"


def test_composition_prompt_renders_the_real_catalog_component_names():
    """The model must receive the catalog's component names, not a token or a copy.

    The composition placeholder and the serving key once disagreed, so the model saw
    ``components: [[catalog_components]]`` and returned an empty message stream,
    which failed validation and degraded every surface to the fallback (D-052).
    """

    from core.a2ui_catalog import published_catalog

    catalog = published_catalog()
    rendered = render(
        load_prompt(Capability.INTERFACE_COMPOSITION).text,
        _render_values(Capability.INTERFACE_COMPOSITION, catalog),
    )
    for name in catalog.component_names():
        assert name in rendered, f"rendered composition prompt omits catalog component {name}"
    assert "[[catalog_components]]" not in rendered
    assert "[[allowed_components]]" not in rendered
