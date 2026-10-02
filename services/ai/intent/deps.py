"""Dependency wiring for intent resolution.

The provider is the pinned Gemini build wrapped by the shared
:class:`~app.provider.FailClosedProvider`, so a client-construction or setup error
degrades to the documented keyword fallback instead of a 500. The retrieval index
resolves the service's single process-wide registry at call time (see
:mod:`app.retrieval`); the google-genai SDK is imported lazily by the provider only
when a call is made, so the service boots and health-checks without the SDK or a
network.

``get_intent_service`` is a FastAPI dependency so tests can swap the model and index
with a deterministic double through ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from app.provider import FailClosedProvider
from app.retrieval import LateBoundRetrievalIndex
from core.config import ModelSettings
from core.provider import GeminiProvider
from core.serving import ModelServing
from intent.service import IntentService

__all__ = ["FailClosedProvider", "build_intent_service", "get_intent_service"]


def build_intent_service(settings: ModelSettings | None = None) -> IntentService:
    """Build the production intent service over the pinned provider build."""

    settings = settings or ModelSettings.from_env()
    serving = ModelServing(
        FailClosedProvider(GeminiProvider(settings)),
        LateBoundRetrievalIndex(),
        settings=settings,
    )
    return IntentService(serving)


@lru_cache(maxsize=1)
def _default_service() -> IntentService:
    return build_intent_service()


def get_intent_service() -> IntentService:
    """FastAPI dependency: the process-wide intent service."""

    return _default_service()
