from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config import CAPABILITY_DECODING, Capability, ModelPath, ModelSettings
from core.errors import ModelTimeout, ProviderUnavailable
from core.provider import GeminiProvider, ModelRequest, ModelUsage


class _FakeTypes:
    @staticmethod
    def GenerateContentConfig(**kwargs):
        return kwargs


class _FakeModels:
    def __init__(self, *, fail: BaseException | None = None, text: str = "{}"):
        self.calls: list[dict] = []
        self._fail = fail
        self._text = text

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail is not None:
            raise self._fail
        return SimpleNamespace(
            text=self._text,
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=30),
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )


class _FakeClient:
    def __init__(self, models: _FakeModels):
        self.models = models


class _FakeSdk:
    types = _FakeTypes()


def _request() -> ModelRequest:
    capability = Capability.INTENT_RESOLUTION
    return ModelRequest(
        capability=capability,
        model_path=ModelPath.FLASH,
        model_id="gemini-3.1-flash-lite",
        prompt_id="intent_resolution",
        prompt_version="v1",
        system_instruction="system",
        contents="contents",
        response_schema={"type": "object"},
        decoding=CAPABILITY_DECODING[capability],
        timeout_seconds=20.0,
    )


def _provider(**kwargs) -> GeminiProvider:
    return GeminiProvider(ModelSettings(api_key="test-key"), sdk=_FakeSdk(), **kwargs)


def test_generate_constrains_output_and_parses_json():
    models = _FakeModels(text='{"intent_type": "unknown", "confidence": 0.2}')
    provider = _provider(client=_FakeClient(models))
    response = provider.generate(_request())
    assert response.parsed == {"intent_type": "unknown", "confidence": 0.2}
    assert response.model_id == "gemini-3.1-flash-lite"
    assert response.usage == ModelUsage(input_tokens=120, output_tokens=30)
    call = models.calls[0]
    assert call["model"] == "gemini-3.1-flash-lite"
    config = call["config"]
    assert config["response_mime_type"] == "application/json"
    assert config["temperature"] == 0.0
    assert config["response_schema"] == {"type": "object"}
    assert "response_json_schema" not in config


def test_generate_prefers_a_full_json_schema_when_supplied():
    """A dynamic output sets ``response_json_schema`` and omits ``response_schema``.

    The composition stream needs ``additionalProperties`` on its message bodies,
    which the Developer API only accepts through ``response_json_schema``; sending
    both would be ambiguous.
    """

    full = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"messages": {"type": "array"}},
        "required": ["messages"],
    }
    request = _request()
    request = ModelRequest(
        capability=request.capability,
        model_path=request.model_path,
        model_id=request.model_id,
        prompt_id=request.prompt_id,
        prompt_version=request.prompt_version,
        system_instruction=request.system_instruction,
        contents=request.contents,
        response_schema=request.response_schema,
        decoding=request.decoding,
        timeout_seconds=request.timeout_seconds,
        response_json_schema=full,
    )
    models = _FakeModels(text='{"messages": []}')
    provider = _provider(client=_FakeClient(models))
    provider.generate(request)
    config = models.calls[0]["config"]
    assert config["response_json_schema"] == full
    assert "response_schema" not in config


def test_non_json_text_is_returned_unparsed():
    provider = _provider(client=_FakeClient(_FakeModels(text="not json")))
    response = provider.generate(_request())
    assert response.parsed is None
    assert response.text == "not json"


def test_timeout_is_classified_as_model_timeout():
    provider = _provider(client=_FakeClient(_FakeModels(fail=TimeoutError())))
    with pytest.raises(ModelTimeout):
        provider.generate(_request())


def test_provider_error_is_classified_as_provider_unavailable():
    provider = _provider(client=_FakeClient(_FakeModels(fail=RuntimeError("boom"))))
    with pytest.raises(ProviderUnavailable):
        provider.generate(_request())


def test_missing_sdk_is_a_provider_failure_not_an_import_error(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "google", None)
    provider = GeminiProvider(ModelSettings(api_key="x"))
    with pytest.raises(ProviderUnavailable):
        provider.generate(_request())


def test_api_key_never_appears_in_the_log(caplog):
    import logging

    secret = "top-secret-key"
    provider = GeminiProvider(
        ModelSettings(api_key=secret),
        sdk=_FakeSdk(),
        client=_FakeClient(_FakeModels(text="{}")),
    )
    with caplog.at_level(logging.INFO):
        provider.generate(_request())
    assert secret not in caplog.text
    assert "model_call" in caplog.text
