from __future__ import annotations

from decimal import Decimal

from core.config import (
    CAPABILITY_DECODING,
    CAPABILITY_MODEL_PATH,
    COST_CEILINGS,
    FLASH_MODEL_ID,
    PRIMARY_MODEL_ID,
    Capability,
    ModelPath,
    ModelSettings,
)


def test_pinned_provider_build_is_fixed():
    assert PRIMARY_MODEL_ID == "gemini-3.1-pro-preview"
    assert FLASH_MODEL_ID == "gemini-3.1-flash-lite"


def test_capability_paths_match_the_high_volume_split():
    assert CAPABILITY_MODEL_PATH[Capability.INTENT_RESOLUTION] is ModelPath.FLASH
    assert CAPABILITY_MODEL_PATH[Capability.DISCOVERY_RANKING] is ModelPath.FLASH
    assert CAPABILITY_MODEL_PATH[Capability.INTERFACE_COMPOSITION] is ModelPath.PRIMARY


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
    assert settings.primary_model_id == PRIMARY_MODEL_ID
    assert settings.flash_model_id == FLASH_MODEL_ID
    assert settings.api_key == ""
    assert settings.timeout_seconds == 20.0


def test_settings_from_env_reads_overrides():
    settings = ModelSettings.from_env(
        {
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL_ID": "custom-primary",
            "GEMINI_FLASH_MODEL_ID": "custom-flash",
            "MODEL_TIMEOUT_SECONDS": "5",
        }
    )
    assert settings.primary_model_id == "custom-primary"
    assert settings.flash_model_id == "custom-flash"
    assert settings.timeout_seconds == 5.0


def test_settings_repr_never_leaks_the_api_key():
    settings = ModelSettings(api_key="super-secret")
    assert "super-secret" not in repr(settings)


def test_blank_env_model_ids_fall_back_to_pinned_values():
    settings = ModelSettings.from_env({"GEMINI_MODEL_ID": "  ", "MODEL_TIMEOUT_SECONDS": "abc"})
    assert settings.primary_model_id == PRIMARY_MODEL_ID
    assert settings.timeout_seconds == 20.0


def test_model_id_for_capability_uses_the_pinned_path():
    settings = ModelSettings()
    assert settings.model_id_for_capability(Capability.INTENT_RESOLUTION) == FLASH_MODEL_ID
    assert settings.model_id_for_capability(Capability.INTERFACE_COMPOSITION) == PRIMARY_MODEL_ID
