"""Wiring for the composition router.

The serving layer is created once per process and stored on ``app.state`` so
tests can override it. :class:`ModelServing` is constructed with the pinned
settings (model IDs, decoding, timeout) and the injected retrieval index.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import Request

from core.config import ModelSettings
from core.provider import GeminiProvider, ModelProvider
from core.retrieval import RetrievalIndex, RetrievedRecord
from core.serving import ModelServing


class EmptyRetrievalIndex:
    """A retrieval index with no records.

    Interface composition is not grounded in the service catalogue: the task
    context reaches the model through the request, not through retrieval. This
    index keeps the serving seam satisfied without inventing catalogue facts.
    """

    def search(self, query: str, *, limit: int) -> Sequence[RetrievedRecord]:
        return []


def build_serving(
    settings: ModelSettings | None = None,
    *,
    provider: ModelProvider | None = None,
) -> ModelServing:
    """Build the process-wide serving layer.

    A provider may be injected for tests; otherwise the pinned Gemini provider is
    built, and an absent SDK degrades to the documented fallback at call time
    rather than failing boot.
    """

    resolved = settings or ModelSettings.from_env()
    model_provider = provider or GeminiProvider(resolved)
    retrieval: RetrievalIndex = EmptyRetrievalIndex()
    return ModelServing(model_provider, retrieval, settings=resolved)


def get_serving(request: Request) -> ModelServing:
    """Return the serving layer stored on the app, creating it lazily."""

    serving = getattr(request.app.state, "serving", None)
    if serving is None:
        settings: ModelSettings | None = getattr(request.app.state, "settings", None)
        serving = build_serving(settings)
        request.app.state.serving = serving
    return serving
