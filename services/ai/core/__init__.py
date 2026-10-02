"""Model serving and evaluation foundation for Sabi.

Import surface for the AI service: pinned model configuration, the structured output
contracts, retrieval and grounding, guardrails, the documented fallbacks, cost
telemetry, and the :class:`~core.serving.ModelServing` facade that runs the
model-backed capabilities.
"""

from __future__ import annotations

from core.config import (
    CAPABILITY_DECODING,
    CAPABILITY_MODEL_PATH,
    COST_CEILINGS,
    FLASH_MODEL_ID,
    INTENT_CONFIDENCE_CUTOFF,
    PRIMARY_MODEL_ID,
    PROMPT_VERSION,
    Capability,
    DecodingSettings,
    ModelPath,
    ModelSettings,
)
from core.errors import (
    ModelError,
    ModelTimeout,
    OutputValidationError,
    ProviderUnavailable,
)
from core.fallback import (
    FALLBACK_CONFIDENCE,
    FALLBACK_SOURCE,
    FallbackResolution,
    fallback_intent,
    keyword_resolution,
)
from core.grounding import (
    GroundingContext,
    GroundingReport,
    amount_is_traceable,
    amounts_in_text,
    build_context,
    ground_intent,
    ground_ranking,
)
from core.guardrails import (
    INTENT_CONFIDENCE_THRESHOLD,
    LANGUAGE_FALLBACK_NOTE,
    RANKING_CONFIDENCE_THRESHOLD,
    SUPPORTED_LANGUAGES,
    CompositionValidation,
    GuardrailOutcome,
    enforce_intent,
    normalize_question,
    validate_composition,
)
from core.prompts import Prompt, load_prompt, render
from core.provider import (
    GeminiProvider,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    parse_json,
)
from core.retrieval import (
    KeywordRetrievalIndex,
    RetrievalIndex,
    RetrievedRecord,
    render_untrusted_block,
)
from core.schemas import (
    CLIENT_COMPONENT_CATALOGUE,
    COMPOSITION_MESSAGE_TYPES,
    DETECTED_LANGUAGES,
    FALLBACK_TASKS,
    INTENT_TYPES,
    LANGUAGES,
    PAYMENT_INTENT_TYPES,
    Intent,
    RankingResult,
    ServiceSummary,
)
from core.serving import (
    CompositionOutcome,
    IntentResolution,
    ModelServing,
    RankingOutcome,
)
from core.telemetry import CostTracker, TaskCost, estimate_cost, price_for

__all__ = [
    "CAPABILITY_DECODING",
    "CAPABILITY_MODEL_PATH",
    "CLIENT_COMPONENT_CATALOGUE",
    "COMPOSITION_MESSAGE_TYPES",
    "COST_CEILINGS",
    "DETECTED_LANGUAGES",
    "FALLBACK_CONFIDENCE",
    "FALLBACK_SOURCE",
    "FALLBACK_TASKS",
    "FLASH_MODEL_ID",
    "INTENT_CONFIDENCE_CUTOFF",
    "INTENT_CONFIDENCE_THRESHOLD",
    "INTENT_TYPES",
    "LANGUAGE_FALLBACK_NOTE",
    "LANGUAGES",
    "PAYMENT_INTENT_TYPES",
    "PRIMARY_MODEL_ID",
    "PROMPT_VERSION",
    "RANKING_CONFIDENCE_THRESHOLD",
    "SUPPORTED_LANGUAGES",
    "Capability",
    "CompositionOutcome",
    "CompositionValidation",
    "CostTracker",
    "DecodingSettings",
    "FallbackResolution",
    "GeminiProvider",
    "GroundingContext",
    "GroundingReport",
    "GuardrailOutcome",
    "Intent",
    "IntentResolution",
    "KeywordRetrievalIndex",
    "ModelError",
    "ModelPath",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ModelServing",
    "ModelSettings",
    "ModelTimeout",
    "ModelUsage",
    "OutputValidationError",
    "Prompt",
    "ProviderUnavailable",
    "RankingOutcome",
    "RankingResult",
    "RetrievalIndex",
    "RetrievedRecord",
    "ServiceSummary",
    "TaskCost",
    "amount_is_traceable",
    "amounts_in_text",
    "build_context",
    "enforce_intent",
    "estimate_cost",
    "fallback_intent",
    "ground_intent",
    "ground_ranking",
    "keyword_resolution",
    "load_prompt",
    "normalize_question",
    "parse_json",
    "price_for",
    "render",
    "render_untrusted_block",
    "validate_composition",
]
