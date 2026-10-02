"""Dependency wiring for discovery ranking.

The provider is the pinned Gemini build, and the retrieval index resolves the
catalogue's process-wide index at call time (see :mod:`ranking.catalogue`). The
google-genai SDK is imported lazily by the provider only when a call is made, so
the service boots and health-checks without the SDK or a network.

``get_ranking_service`` is a FastAPI dependency so tests can swap the model and
index with a deterministic double through ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from core.config import ModelSettings
from core.provider import GeminiProvider
from core.serving import ModelServing
from ranking.catalogue import LateBoundRetrievalIndex
from ranking.service import RankingService


def build_ranking_service(settings: ModelSettings | None = None) -> RankingService:
    """Build the production ranking service over the pinned provider build."""

    settings = settings or ModelSettings.from_env()
    serving = ModelServing(
        GeminiProvider(settings),
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
