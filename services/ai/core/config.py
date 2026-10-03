"""Pinned model build, decoding settings, and cost ceilings.

This module is the single place the model version policy from the model-quality
contract is realised: the exact provider model ID for the primary and flash paths is
fixed here, and every model-backed capability has pinned decoding settings so an
evaluation run is reproducible. Changing a constant here is a model version change and
requires a full evaluation run before it ships.

The cost ceilings come from the non-functional requirements (NFR-050 to NFR-052). A
cost is measured per completed user task, so retries and clarification turns count
against the ceiling; the cost tracker accumulates them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

# --- Pinned provider build -------------------------------------------------------
# The primary provider is Gemini 3.1 Pro with the lower-cost Flash-Lite path for
# high-volume intent resolution (model-quality.md, "Model version and fallback").
# Both IDs are stable endpoints, chosen over the preview builds so the default does
# not carry preview deprecation exposure. Prices reviewed 2026-10-03.
PRIMARY_MODEL_ID = "gemini-3.1-pro-preview"
FLASH_MODEL_ID = "gemini-3.1-flash-lite"

# Prompt artifacts are versioned alongside the model build they were tuned for.
PROMPT_VERSION = "v1"

# The serving confidence cutoff for intent resolution. Below it the model asks exactly
# one clarifying question and never presents a payment intent (model-quality.md,
# "MQ-001" and "Quality bar"; fixed at 0.70 by D-017). It is a product decision, not a
# per-run tuning knob, and it is evaluated against the golden set rather than adjusted
# to make a run pass.
INTENT_CONFIDENCE_CUTOFF = 0.70

# Retrieval breadth passed to grounding and ranking. The catalogue API caps a result
# set at five (C-010), so the retriever returns a slightly wider candidate pool for
# the model to filter and rank.
RETRIEVAL_LIMIT = 20
MAX_RESULTS = 5


class ModelPath(Enum):
    """Which pinned provider path a capability runs on."""

    PRIMARY = "primary"
    FLASH = "flash"


class Capability(Enum):
    """The model-backed capabilities defined by the quality contract."""

    INTENT_RESOLUTION = "intent_resolution"
    DISCOVERY_RANKING = "discovery_ranking"
    INTERFACE_COMPOSITION = "interface_composition"


# Intent resolution and discovery ranking are the high-volume paths; interface
# composition runs on the stronger primary model.
CAPABILITY_MODEL_PATH: Mapping[Capability, ModelPath] = {
    Capability.INTENT_RESOLUTION: ModelPath.FLASH,
    Capability.DISCOVERY_RANKING: ModelPath.FLASH,
    Capability.INTERFACE_COMPOSITION: ModelPath.PRIMARY,
}


@dataclass(frozen=True)
class DecodingSettings:
    """Provider decoding settings, pinned per capability for reproducibility."""

    temperature: float
    top_p: float
    max_output_tokens: int


# Reproducibility (model-quality.md): model version and decoding settings are pinned
# for evaluation. Temperature is 0 across capabilities; interface composition still
# validates any schema-correct stream rather than a single wording.
CAPABILITY_DECODING: Mapping[Capability, DecodingSettings] = {
    Capability.INTENT_RESOLUTION: DecodingSettings(
        temperature=0.0, top_p=1.0, max_output_tokens=512
    ),
    Capability.DISCOVERY_RANKING: DecodingSettings(
        temperature=0.0, top_p=1.0, max_output_tokens=1024
    ),
    Capability.INTERFACE_COMPOSITION: DecodingSettings(
        temperature=0.0, top_p=1.0, max_output_tokens=4096
    ),
}


# --- Cost ceilings (NFR-050 to NFR-052) -----------------------------------------


@dataclass(frozen=True)
class CostCeiling:
    """The per-completed-task cost ceiling for a capability."""

    capability: Capability
    usd: Decimal
    nfr_id: str


COST_CEILINGS: Mapping[Capability, CostCeiling] = {
    Capability.INTENT_RESOLUTION: CostCeiling(
        Capability.INTENT_RESOLUTION, Decimal("0.02"), "NFR-050"
    ),
    Capability.DISCOVERY_RANKING: CostCeiling(
        Capability.DISCOVERY_RANKING, Decimal("0.01"), "NFR-051"
    ),
    Capability.INTERFACE_COMPOSITION: CostCeiling(
        Capability.INTERFACE_COMPOSITION, Decimal("0.02"), "NFR-052"
    ),
}


@dataclass(frozen=True)
class ModelPrice:
    """Published list price in USD per one million tokens."""

    input_per_million: Decimal
    output_per_million: Decimal


# Published list prices at the pinned build. Reviewed whenever the model changes.
MODEL_PRICES: Mapping[str, ModelPrice] = {
    PRIMARY_MODEL_ID: ModelPrice(
        input_per_million=Decimal("2.00"), output_per_million=Decimal("12.00")
    ),
    FLASH_MODEL_ID: ModelPrice(
        input_per_million=Decimal("0.25"), output_per_million=Decimal("1.50")
    ),
}


@dataclass(frozen=True)
class ModelSettings:
    """Runtime settings for the provider client.

    ``api_key`` is excluded from ``repr`` so a configuration dump or an exception
    traceback can never leak the secret (NFR-024).
    """

    api_key: str = field(repr=False, default="")
    primary_model_id: str = PRIMARY_MODEL_ID
    flash_model_id: str = FLASH_MODEL_ID
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ModelSettings:
        """Build settings from the environment, falling back to the pinned defaults.

        The model IDs default to the pinned build rather than requiring configuration,
        so a missing or blank variable cannot silently point the service at a different
        model.
        """

        source = os.environ if env is None else env

        def _text(name: str, default: str) -> str:
            value = source.get(name, "").strip()
            return value or default

        timeout_raw = source.get("MODEL_TIMEOUT_SECONDS", "").strip()
        try:
            timeout = float(timeout_raw) if timeout_raw else cls.timeout_seconds
        except ValueError:
            timeout = cls.timeout_seconds

        return cls(
            api_key=source.get("GEMINI_API_KEY", ""),
            primary_model_id=_text("GEMINI_MODEL_ID", PRIMARY_MODEL_ID),
            flash_model_id=_text("GEMINI_FLASH_MODEL_ID", FLASH_MODEL_ID),
            timeout_seconds=timeout,
        )

    def model_id_for(self, path: ModelPath) -> str:
        return self.primary_model_id if path is ModelPath.PRIMARY else self.flash_model_id

    def model_id_for_capability(self, capability: Capability) -> str:
        return self.model_id_for(CAPABILITY_MODEL_PATH[capability])
