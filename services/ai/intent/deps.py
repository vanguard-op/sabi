"""Dependency wiring for intent resolution.

The provider is the pinned Gemini build, and the retrieval index resolves the
catalogue's process-wide index at call time (see :mod:`intent.catalogue`). The
google-genai SDK is imported lazily by the provider only when a call is made, so the
service boots and health-checks without the SDK or a network.

``get_intent_service`` is a FastAPI dependency so tests can swap the model and index
with a deterministic double through ``app.dependency_overrides``.
"""

from __future__ import annotations

from functools import lru_cache

from core.config import ModelSettings
from core.errors import ModelError, ProviderUnavailable
from core.provider import GeminiProvider, ModelProvider, ModelRequest, ModelResponse
from core.serving import ModelServing
from intent.catalogue import LateBoundRetrievalIndex
from intent.service import IntentService


class FailClosedProvider:
    """Wrap a provider so any setup failure degrades to the documented fallback.

    The pinned provider builds its SDK client lazily, and that client can raise before
    the model call (for example when no API key is configured). Those failures are
    provider failures, not contract errors: this wrapper turns them into
    :class:`~core.errors.ProviderUnavailable` so the serving layer runs the keyword
    fallback with mandatory confirmation instead of returning a 500.
    """

    def __init__(self, inner: ModelProvider) -> None:
        self._inner = inner

    def generate(self, request: ModelRequest) -> ModelResponse:
        try:
            return self._inner.generate(request)
        except ModelError:
            raise
        except Exception as exc:  # noqa: BLE001 - any SDK/setup error is a provider failure
            raise ProviderUnavailable("model provider failed to initialise") from exc


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
