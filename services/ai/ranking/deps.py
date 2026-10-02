"""Dependency wiring for discovery ranking.

The provider is the pinned Gemini build wrapped by the shared
:class:`~app.provider.FailClosedProvider`, so a client-construction or setup error
degrades to the documented keyword fallback rather than a 500. The retrieval index
resolves the service's single process-wide registry at call time (see
:mod:`app.retrieval`); the google-genai SDK is imported lazily by the provider only
when a call is made, so the service boots and health-checks without the SDK or a
network.

``get_ranking_service`` is a FastAPI dependency so tests can swap the model and index
with a deterministic double through ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from app.provider import FailClosedProvider
from app.retrieval import LateBoundRetrievalIndex
from core.config import ModelSettings
from core.provider import GeminiProvider
from core.serving import ModelServing
from ranking.service import RankingService

__all__ = ["build_ranking_service", "get_ranking_service"]


def build_ranking_service(settings: ModelSettings | None = None) -> RankingService:
    """Build the production ranking service over the pinned provider build."""

    settings = settings or ModelSettings.from_env()
    serving = ModelServing(
        FailClosedProvider(GeminiProvider(settings)),
        LateBoundRetrievalIndex(),
        settings=settings,
    )
    return RankingService(serving)


@lru_cache(maxsize=1)
def _default_service() -> RankingService:
    return build_ranking_service()


def get_ranking_service() -> RankingService:
    """FastAPI dependency: the process-wide ranking service."""

    return _default_service()
