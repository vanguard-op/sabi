"""Dependency wiring for payment-intent extraction.

The provider is the pinned Gemini build wrapped by the shared
:class:`~app.provider.FailClosedProvider`, so a client-construction or setup error
degrades to the documented keyword fallback rather than a 500. The retrieval index
resolves the service's single process-wide registry at call time (see
:mod:`app.retrieval`); the google-genai SDK is imported lazily by the provider only
when a call is made, so the service boots and health-checks without the SDK or a
network.

``get_payment_intent_service`` is a FastAPI dependency so tests can swap the model and
index with a deterministic double through ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from app.provider import FailClosedProvider
from app.retrieval import LateBoundRetrievalIndex
from core.config import ModelSettings
from core.provider import GeminiProvider, ModelProvider
from payment_intent.service import PaymentIntentService

__all__ = [
    "build_payment_intent_service",
    "get_payment_intent_service",
]


def build_payment_intent_service(
    settings: ModelSettings | None = None,
    *,
    provider: ModelProvider | None = None,
) -> PaymentIntentService:
    """Build the production extraction service over the pinned provider build."""

    resolved = settings or ModelSettings.from_env()
    model_provider = provider or FailClosedProvider(GeminiProvider(resolved))
    return PaymentIntentService(model_provider, LateBoundRetrievalIndex(), settings=resolved)


@lru_cache(maxsize=1)
def _default_service() -> PaymentIntentService:
    return build_payment_intent_service()


def get_payment_intent_service() -> PaymentIntentService:
    """FastAPI dependency: the process-wide extraction service."""

    return _default_service()
