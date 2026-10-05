from __future__ import annotations

from decimal import Decimal

import pytest

from core.config import (
    CAPABILITY_DECODING,
    CAPABILITY_MODEL_PATH,
    COST_CEILINGS,
    FLASH_MODEL_ID,
    MODEL_PRICES,
    Capability,
    ModelPath,
    ModelSettings,
)


def test_pinned_provider_build_is_fixed():
    assert FLASH_MODEL_ID == "gemini-3.1-flash-lite"


def test_the_preview_primary_path_is_removed():
    # D-054 / model-quality.md: there is no primary or preview model behind any
    # capability. The constant and the path member are gone so the preview build cannot
    # be reintroduced by a one-line routing change.
    import core.config

    assert not hasattr(core.config, "PRIMARY_MODEL_ID")
    assert [member.name for member in ModelPath] == ["FLASH"]


def test_every_capability_runs_on_the_one_stable_path():
    for capability in Capability:
        assert CAPABILITY_MODEL_PATH[capability] is ModelPath.FLASH


def test_only_the_pinned_build_is_priced():
    assert set(MODEL_PRICES) == {FLASH_MODEL_ID}


def test_decoding_is_pinned_for_every_capability():
    assert set(CAPABILITY_DECODING) == set(Capability)
    for decoding in CAPABILITY_DECODING.values():
        assert decoding.temperature == 0.0
        assert decoding.top_p == 1.0
        assert decoding.max_output_tokens > 0


def test_cost_ceilings_match_the_nfrs():
    ceilings = {capability: ceiling.usd for capability, ceiling in COST_CEILINGS.items()}
    assert ceilings[Capability.INTENT_RESOLUTION] == Decimal("0.02")
    assert ceilings[Capability.DISCOVERY_RANKING] == Decimal("0.01")
    assert ceilings[Capability.INTERFACE_COMPOSITION] == Decimal("0.02")
    assert COST_CEILINGS[Capability.INTENT_RESOLUTION].nfr_id == "NFR-050"


def test_settings_from_env_default_to_the_pinned_build():
    settings = ModelSettings.from_env({})
    assert settings.flash_model_id == FLASH_MODEL_ID
    assert settings.api_key == ""
    assert settings.timeout_seconds == 20.0


def test_settings_from_env_reads_overrides():
    settings = ModelSettings.from_env(
        {
            "GEMINI_API_KEY": "test-key",
            "GEMINI_FLASH_MODEL_ID": "custom-flash",
            "MODEL_TIMEOUT_SECONDS": "5",
        }
    )
    assert settings.flash_model_id == "custom-flash"
    assert settings.timeout_seconds == 5.0


def test_settings_repr_never_leaks_the_api_key():
    settings = ModelSettings(api_key="super-secret")
    assert "super-secret" not in repr(settings)


def test_blank_env_model_ids_fall_back_to_pinned_values():
    settings = ModelSettings.from_env(
        {"GEMINI_FLASH_MODEL_ID": "  ", "MODEL_TIMEOUT_SECONDS": "abc"}
    )
    assert settings.flash_model_id == FLASH_MODEL_ID
    assert settings.timeout_seconds == 20.0


def test_model_id_for_capability_uses_the_pinned_path():
    settings = ModelSettings()
    for capability in Capability:
        assert settings.model_id_for_capability(capability) == FLASH_MODEL_ID


def test_model_id_for_rejects_an_unknown_path():
    settings = ModelSettings()
    with pytest.raises(ValueError):
        settings.model_id_for("primary")  # type: ignore[arg-type]
