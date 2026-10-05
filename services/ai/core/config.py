"""Pinned model build, decoding settings, and cost ceilings.

This module is the single place the model version policy from the model-quality
contract is realised: the one exact provider model ID every capability runs on is
fixed here, and every model-backed capability has pinned decoding settings so an
evaluation run is reproducible. Changing a constant here is a model version change and
requires a full evaluation run before it ships.

Every judged capability runs on the same stable pinned build; there is deliberately no
primary or preview path, so a preview model cannot be reintroduced behind a capability
without a model version change to this file (model-quality.md, "Model version and
fallback").

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
# Every model-backed capability runs on the stable Flash-Lite build
# (model-quality.md, "Model version and fallback"; D-054). The ID is a stable endpoint,
# not a preview build, so no capability carries preview deprecation exposure. The
# single path is deliberate: no preview/primary model is pinned, so it cannot be
# reintroduced by a capability routing change. Price reviewed 2026-10-05.
FLASH_MODEL_ID = "gemini-3.1-flash-lite"

# Prompt artifacts are versioned alongside the model build they were tuned for.
# ``PROMPT_VERSION`` is the default; a capability whose prompt behavior changes gets
# its own version in ``PROMPT_VERSIONS`` rather than editing a shipped artifact in
# place, so an evaluation run is always reproducible against the exact prompt text.
PROMPT_VERSION = "v1"
# Intent resolution moved to ``v4`` for the conversational contract: the model authors
# the user-facing ``reply`` in natural language (greeting, clarifying question,
# refusal, non-resolving reply) plus the reduced machine-actionable intent, and the
# request locale is bound as the language to reply in. The v3 template held the
# structured-only contract (``language``/``clarifying_question`` in the object).
INTENT_PROMPT_VERSION = "v4"
# Interface composition moved to ``v2`` when the composed surface became the task
# mechanism for every task and record type (MQ-003, FEAT-011): the task enum gained
# ``verification`` and ``recovery``, and ``receipt`` now also composes a resolved
# record the user asked about, not only a post-payment service payment. It moved to
# ``v3`` with A2UI adoption (D-051): the payload is a real A2UI v0.9 message stream
# composed against the published Sabi catalog, the surface names the negotiated
# ``catalogId``, and the allowed components come from that catalog, not a server-side
# copy. It moved to ``v4`` when the required-property rule was made satisfiable: the
# prompt now states each task's required context (rendered from the same contract the
# serving layer guards on) and scopes the empty-stream escape hatch to a task the
# catalog genuinely cannot represent, so a composable context is never answered with
# an empty surface. It moved to ``v5`` when the provider response schema was
# catalog-derived: the prompt now renders the component names one per line (a
# comma-joined list was echoed into a component name) and states that a component's
# required properties are flat properties on the component rather than routed through
# ``updateDataModel``, matching what the pre-send validator checks.
INTERFACE_COMPOSITION_PROMPT_VERSION = "v5"

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
    """Which pinned provider path a capability runs on.

    One stable build backs every capability (D-054), so there is a single path. The
    enum is kept so a call still names the path it used, and so a future path is an
    explicit addition here rather than an implicit fallback.
    """

    FLASH = "flash"


class Capability(Enum):
    """The model-backed capabilities defined by the quality contract."""

    INTENT_RESOLUTION = "intent_resolution"
    DISCOVERY_RANKING = "discovery_ranking"
    INTERFACE_COMPOSITION = "interface_composition"


# Every capability runs on the one stable pinned build. Interface composition runs
# while the user waits on every surface, so it is on the cheaper stable path rather
# than the removed preview build (D-054).
CAPABILITY_MODEL_PATH: Mapping[Capability, ModelPath] = {
    Capability.INTENT_RESOLUTION: ModelPath.FLASH,
    Capability.DISCOVERY_RANKING: ModelPath.FLASH,
    Capability.INTERFACE_COMPOSITION: ModelPath.FLASH,
}

# Per-capability prompt artifact versions. Intent resolution moved to ``v2`` to carry
# conversation history, ``non_command``, and the three-clarification bound; the other
# capabilities remain on the shared default.
PROMPT_VERSIONS: Mapping[Capability, str] = {
    Capability.INTENT_RESOLUTION: INTENT_PROMPT_VERSION,
    Capability.INTERFACE_COMPOSITION: INTERFACE_COMPOSITION_PROMPT_VERSION,
}


def prompt_version_for(capability: Capability) -> str:
    """The prompt artifact version a capability is pinned to."""

    return PROMPT_VERSIONS.get(capability, PROMPT_VERSION)


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
# Only the pinned build is priced; an unpriced model resolves to zero cost, so no
# preview model can quietly accrue cost without a price entry being added here.
MODEL_PRICES: Mapping[str, ModelPrice] = {
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
            flash_model_id=_text("GEMINI_FLASH_MODEL_ID", FLASH_MODEL_ID),
            timeout_seconds=timeout,
        )

    def model_id_for(self, path: ModelPath) -> str:
        """The provider model ID for a path.

        There is one stable path today, so it always resolves to the pinned build.
        An unknown path is a programming error rather than a silent fallback.
        """

        if path is not ModelPath.FLASH:
            raise ValueError(f"unknown model path: {path!r}")
        return self.flash_model_id

    def model_id_for_capability(self, capability: Capability) -> str:
        return self.model_id_for(CAPABILITY_MODEL_PATH[capability])
