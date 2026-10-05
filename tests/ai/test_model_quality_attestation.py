"""Model-quality attestation for the Phase 1 gate.

The judged bars (MQ-001, MQ-001R, MQ-002, MQ-002R, MQ-003, MQ-004) cannot be
measured by a deterministic test: they need the golden datasets, judges, and
reply-rubric review that model-quality.md states. What
this module *can* verify is the reproducible substrate the bars are measured
against -- the pinned model build and decoding settings -- and it records, as an
explicit failure, that the measurement harness is not present in this delivery. A
judged bar with no dataset and no harness is reported, never assumed.

Reference: model-quality.md "Quality bar", "Model version and fallback",
"Measurement and verification".
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_AI_ROOT = _ROOT / "services" / "ai"


def test_pinned_model_build_matches_the_quality_contract() -> None:
    """The single stable pinned build; the code must match the decision of record.

    D-054 removes the primary/preview path entirely: every capability -- intent
    resolution, discovery ranking, interface composition, and Nigerian-language
    understanding -- runs on the stable, lower-cost ``gemini-3.1-flash-lite``, so no
    capability carries preview deprecation exposure. ``model-quality.md`` "Model
    version and fallback" names the same single build. This is a substrate check,
    not the MQ accuracy bar, which remains unmeasured and reported separately.
    """

    import core.config
    from core.config import FLASH_MODEL_ID

    assert FLASH_MODEL_ID == "gemini-3.1-flash-lite"
    # The removed preview path must not resurface as a constant or a member: a
    # routing change alone cannot reintroduce it (D-054).
    assert not hasattr(core.config, "PRIMARY_MODEL_ID")


def test_decoding_is_pinned_temperature_zero_for_every_capability() -> None:
    """Reproducibility: decoding is pinned for evaluation (temperature 0, top_p 1)."""

    from core.config import CAPABILITY_DECODING, Capability

    assert set(CAPABILITY_DECODING) == set(Capability)
    for settings in CAPABILITY_DECODING.values():
        assert settings.temperature == 0.0
        assert settings.top_p == 1.0


def test_serving_confidence_cutoff_is_the_product_decision() -> None:
    """D-017 / model-quality.md: the one serving cutoff is 0.70."""

    from core.config import INTENT_CONFIDENCE_CUTOFF

    assert INTENT_CONFIDENCE_CUTOFF == 0.70


def test_cost_ceilings_match_the_nfr_contract() -> None:
    from decimal import Decimal

    from core.config import COST_CEILINGS, Capability

    assert COST_CEILINGS[Capability.INTENT_RESOLUTION].usd == Decimal("0.02")
    assert COST_CEILINGS[Capability.DISCOVERY_RANKING].usd == Decimal("0.01")
    assert COST_CEILINGS[Capability.INTERFACE_COMPOSITION].usd == Decimal("0.02")


def test_every_capability_runs_on_the_one_stable_model_path() -> None:
    from core.config import CAPABILITY_MODEL_PATH, Capability, ModelPath

    # D-054: interface composition moves off the removed preview pro path onto the
    # same stable flash build as intent resolution and the rest, so there is a
    # single path for every capability.
    assert [member.name for member in ModelPath] == ["FLASH"]
    for capability in Capability:
        assert CAPABILITY_MODEL_PATH[capability] is ModelPath.FLASH


def test_golden_set_and_evaluation_harness_are_absent_from_this_delivery() -> None:
    """The MQ bars have no dataset or harness in the repo, so they cannot be run.

    model-quality.md requires an evaluation run before every release against stated
    datasets, and a capability that authors a reply carries two bars: a structured
    bar (MQ-001/MQ-002) and a reply-rubric bar (MQ-001R/MQ-002R). No such dataset,
    harness, judge, or scored run exists under ``services/ai`` in this delivery, so
    every MQ bar is unverified, including the reply-rubric rows. This test fails to
    surface that gap rather than imply a pass.
    """

    candidates = [
        path
        for path in _AI_ROOT.rglob("*")
        if path.is_file()
        and any(
            token in path.name.lower()
            for token in ("golden", "eval_", "_eval", "evaluation", "dataset")
        )
        and ".venv" not in path.parts
        and "__pycache__" not in path.parts
    ]
    assert not candidates, (
        "Expected no evaluation harness in this delivery; found: "
        f"{[str(p.relative_to(_ROOT)) for p in candidates]}"
    )
    pytest.fail(
        "MQ-001, MQ-001R, MQ-002, MQ-002R, MQ-003, and MQ-004 quality bars are unverified: "
        "model-quality.md requires golden-set evaluation runs (1,000 utterances / 500 queries "
        "/ 300 flows) plus reply-rubric review on the reply-bearing sets, but this delivery "
        "ships no dataset, harness, judge, or scored result. Reported as a doc/DoD gap."
    )
