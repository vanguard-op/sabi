"""Provider integration for the pinned model build.

:class:`ModelProvider` is the seam the serving layer depends on. The concrete
:class:`GeminiProvider` wraps the google-genai SDK; it is constructed with an injectable
SDK module and client so tests run against a deterministic double without the network
or the SDK installed. No prompt content, user data, or credential is ever logged.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from core.config import (
    Capability,
    DecodingSettings,
    ModelPath,
    ModelSettings,
)
from core.errors import ModelTimeout, OutputValidationError, ProviderUnavailable

logger = logging.getLogger("core.provider")


@dataclass(frozen=True)
class ModelUsage:
    """Token usage for one provider call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ModelRequest:
    """One constrained generation request.

    ``contents`` already contains the rendered prompt with untrusted retrieved data
    clearly delimited; the provider does not interpret it.
    """

    capability: Capability
    model_path: ModelPath
    model_id: str
    prompt_id: str
    prompt_version: str
    system_instruction: str
    contents: str
    response_schema: Mapping[str, Any]
    decoding: DecodingSettings
    timeout_seconds: float


@dataclass(frozen=True)
class ModelResponse:
    """A provider response, parsed to JSON where possible."""

    text: str
    parsed: Any
    model_id: str
    usage: ModelUsage
    latency_ms: int
    finish_reason: str | None = None


class ModelProvider(Protocol):
    """The model call the serving layer makes."""

    def generate(self, request: ModelRequest) -> ModelResponse: ...


def parse_json(text: str) -> Any:
    """Parse provider JSON text, raising a contract error when it is not JSON.

    The serving layer converts this into the capability fallback.
    """

    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise OutputValidationError("provider response was not valid JSON") from exc


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    return "timeout" in type(exc).__name__.lower()


class GeminiProvider:
    """google-genai implementation of :class:`ModelProvider`.

    ``sdk`` and ``client`` are injectable so the integration is exercised without the
    real SDK or network. When omitted, the SDK is imported lazily and the client is
    created on first use; an absent SDK is reported as a provider failure so the
    documented fallback runs instead of the service crashing at import.
    """

    def __init__(
        self,
        settings: ModelSettings,
        *,
        sdk: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._sdk = sdk
        self._client = client

    def _load_sdk(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        try:  # pragma: no cover - exercised only when the SDK is installed
            from google import genai as sdk
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("google-genai SDK is not available") from exc
        self._sdk = sdk
        return sdk

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        sdk = self._load_sdk()
        self._client = sdk.Client(api_key=self._settings.api_key)
        return self._client

    def generate(self, request: ModelRequest) -> ModelResponse:
        sdk = self._load_sdk()
        client = self._get_client()
        types = sdk.types
        config = types.GenerateContentConfig(
            system_instruction=request.system_instruction,
            response_mime_type="application/json",
            response_schema=request.response_schema,
            temperature=request.decoding.temperature,
            top_p=request.decoding.top_p,
            max_output_tokens=request.decoding.max_output_tokens,
        )

        started = time.perf_counter()
        try:
            raw = client.models.generate_content(
                model=request.model_id,
                contents=request.contents,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 - classified below, re-raised
            if _is_timeout(exc):
                raise ModelTimeout("model call timed out") from exc
            raise ProviderUnavailable("model call failed") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = getattr(raw, "text", None) or ""
        usage = _usage_from(raw)
        finish_reason = _finish_reason_from(raw)
        parsed: Any = None
        if text:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None

        # Structure and token counts only; never the prompt or the response body.
        logger.info(
            "model_call capability=%s model=%s prompt=%s/%s latency_ms=%d "
            "input_tokens=%d output_tokens=%d",
            request.capability.value,
            request.model_id,
            request.prompt_id,
            request.prompt_version,
            latency_ms,
            usage.input_tokens,
            usage.output_tokens,
        )

        return ModelResponse(
            text=text,
            parsed=parsed,
            model_id=request.model_id,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )


def _usage_from(raw: Any) -> ModelUsage:
    metadata = getattr(raw, "usage_metadata", None)
    if metadata is None:
        return ModelUsage()
    return ModelUsage(
        input_tokens=int(getattr(metadata, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(metadata, "candidates_token_count", 0) or 0),
    )


def _finish_reason_from(raw: Any) -> str | None:
    candidates = getattr(raw, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    return str(reason) if reason is not None else None
