"""Wiring for the composition router.

The serving layer is created once per process and stored on ``app.state`` so tests
can override it. :class:`~core.serving.ModelServing` is constructed with the pinned
settings (model IDs, decoding, timeout), the shared fail-closed provider wrapper, and
the service's single retrieval registry.

Interface composition is grounded in the task context it receives, not in the
catalogue, so it never queries the registry; binding the shared index anyway keeps
every model-backed feature wired through one retrieval seam (see :mod:`app.retrieval`)
rather than each package owning a private index.
"""

from __future__ import annotations

from fastapi import Request

from app.provider import FailClosedProvider
from app.retrieval import LateBoundRetrievalIndex
from core.config import ModelSettings
from core.provider import GeminiProvider, ModelProvider
from core.serving import ModelServing


def build_serving(
    settings: ModelSettings | None = None,
    *,
    provider: ModelProvider | None = None,
) -> ModelServing:
    """Build the process-wide serving layer.

    A provider may be injected for tests; otherwise the pinned Gemini provider is
    built and wrapped fail-closed, so an SDK or client-construction error degrades to
    the documented fallback at call time rather than failing boot or returning a 500.
    """

    resolved = settings or ModelSettings.from_env()
    model_provider = provider or FailClosedProvider(GeminiProvider(resolved))
    return ModelServing(model_provider, LateBoundRetrievalIndex(), settings=resolved)


def get_serving(request: Request) -> ModelServing:
    """Return the serving layer stored on the app, creating it lazily."""

    serving = getattr(request.app.state, "serving", None)
    if serving is None:
        settings: ModelSettings | None = getattr(request.app.state, "settings", None)
        serving = build_serving(settings)
        request.app.state.serving = serving
    return serving
