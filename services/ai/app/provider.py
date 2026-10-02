"""Shared provider wrapper that fails closed to the documented fallback.

The pinned provider builds its SDK client lazily, and that construction can fail
before a call is made (for example when no API key is configured, or the SDK is
absent). Those are provider failures, not contract errors: they must degrade to the
keyword and search fallback with mandatory confirmation rather than surfacing a 500
(model-quality.md, "Provider failure").

Every model-backed feature wraps its provider in :class:`FailClosedProvider`, so the
same guarantee holds for intent resolution (C-009), discovery ranking (C-010), and
interface composition (C-012). A :class:`~core.errors.ModelError` raised by the
provider is preserved; any other exception is classified as
:class:`~core.errors.ProviderUnavailable`.
"""

from __future__ import annotations

from core.errors import ModelError, ProviderUnavailable
from core.provider import ModelProvider, ModelRequest, ModelResponse


class FailClosedProvider:
    """Wrap a provider so any setup or client-construction failure degrades.

    The serving layer treats :class:`~core.errors.ProviderUnavailable` (and its
    timeout subtype) as the signal to run the fallback, so converting an unexpected
    SDK error here keeps the refusal behavior uniform across capabilities.
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
