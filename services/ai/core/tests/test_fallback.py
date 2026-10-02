from __future__ import annotations

from core.fallback import FALLBACK_SOURCE, fallback_intent, keyword_resolution


def test_keyword_resolution_maps_catalogue_records(catalogue):
    resolution = keyword_resolution("electricity bill", catalogue)
    assert resolution.source == FALLBACK_SOURCE
    assert [item.service_id for item in resolution.candidates] == ["svc-electric"]
    assert resolution.candidates[0].collecting_body


def test_keyword_resolution_returns_nothing_on_no_match(catalogue):
    resolution = keyword_resolution("airtime topup", catalogue)
    assert resolution.candidates == ()


def test_fallback_intent_is_unresolved_and_requires_confirmation(catalogue):
    resolution = keyword_resolution("electricity bill", catalogue)
    intent = fallback_intent("electricity bill", resolution)
    assert intent.intent_type == "unknown"
    assert intent.confidence == 0.0
    assert intent.clarifying_question is not None
    assert "Ikeja Electric" in intent.clarifying_question


def test_fallback_intent_without_candidates_still_asks(catalogue):
    resolution = keyword_resolution("unknown thing", catalogue)
    intent = fallback_intent("unknown thing", resolution)
    assert intent.intent_type == "unknown"
    assert "biller or agency" in intent.clarifying_question
