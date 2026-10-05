"""Live-provider contract test for composed surfaces (C-012, MQ-003; D-052).

Three successive prompt, schema, and validator bugs reached staging because the
mocked suite cannot observe the model's actual output. This test exercises the real
provider against every composition task and asserts the same things the agent-side
pre-send validator does: a non-empty A2UI v0.9 stream that conforms to the published
Sabi catalog and is marked ``source: model`` (not the same-task fallback).

Gating (D-052): the test runs only when ``GEMINI_API_KEY`` is present; without it the
test is **skipped**, never silently passed, so a green run is honest about what it
covered. It deliberately does not use the fail-closed provider wrapper: a stream that
fails validation after a successful model response raises or fails the assertion here
rather than degrading to a fallback nobody sees.

Two failure kinds are told apart. A *systematic* composition failure (the provider
answered, but the stream was empty or invalid) always fails the test — that is the bug
class this test exists to catch. A *transient* provider transport failure (the SDK
raised, or returned no text at all) is retried a bounded number of times and then
skipped: it is an environment fault, not a prompt or schema regression, and reporting
it as a skip keeps the signal honest instead of turning a flaky network into a red
build.

Run it with ``pytest -m real_model`` (or ``pytest composition/tests/test_real_model.py``)
where a key is available; it is selected by the ``real_model`` marker registered in
``pyproject.toml``. A CI job that provides ``GEMINI_API_KEY`` exercises it; a job
without one reports the cases as skipped.
"""

from __future__ import annotations

import os

import pytest

from core.a2ui import validate_a2ui_stream
from core.a2ui_catalog import published_catalog
from core.config import FLASH_MODEL_ID, ModelSettings
from core.provider import GeminiProvider, ModelProvider, ModelRequest, ModelResponse
from core.retrieval import KeywordRetrievalIndex
from core.serving import MODEL_SOURCE, ModelServing

pytestmark = pytest.mark.real_model

_CATALOG = published_catalog()

# Instantaneous provider failures are retried before a task is reported skipped; a
# systematic composition failure is never retried, because it is deterministic and
# retrying would only delay the report.
_TRANSIENT_ATTEMPTS = 3

# A context that carries every required field of every task (``TASK_CONTEXT_FIELDS``),
# so the serving layer reaches the model instead of taking the missing-context
# fallback. The values are plausible Nigerian payment data; the test asserts the
# stream's shape, not its wording. `receipt` carries the optional fields a real
# receipt record has (C-023/C-024: `kind`, `status`), which is the input that exposed
# the open-schema degeneration.
_TASK_CONTEXTS: dict[str, dict] = {
    "confirmation": {
        "serviceId": "svc-ikeja-electric",
        "payee": "Ikeja Electric",
        "amount": 500000,
        "currency": "NGN",
        "reference": "IE-8891",
    },
    "amount_entry": {"currency": "NGN", "minimum": 10000, "maximum": 5000000},
    "receipt": {
        "receiptId": "rcpt-9",
        "reference": "IE-8891",
        "payee": "Ikeja Electric",
        "amount": 500000,
        "currency": "NGN",
        "kind": "official_e_receipt",
        "status": "settled",
    },
    "discovery": {
        "results": [
            {
                "serviceId": "svc-ikeja-electric",
                "name": "Ikeja Electric",
                "collectingBody": "Ikeja Electricity Distribution Company",
                "category": "electricity",
                "status": "active",
            },
            {
                "serviceId": "svc-eko-electric",
                "name": "Eko Electric",
                "collectingBody": "Eko Electricity Distribution Company",
                "category": "electricity",
                "status": "active",
            },
        ]
    },
    "verification": {"status": "pending", "reference": "V-1"},
    "recovery": {"status": "failed", "reference": "CASE-1", "reason": "rail timed out"},
}


class _ObservedProvider(ModelProvider):
    """A real provider that records whether a call was answered or failed transiently.

    The composition fallback hides the difference between "the model produced an
    invalid stream" (a regression) and "the provider call failed" (an environment
    fault). Wrapping the real provider makes that difference observable to the test.
    """

    def __init__(self, inner: ModelProvider) -> None:
        self._inner = inner
        self.answered = False
        self.transient_error: BaseException | None = None
        self.last_response: ModelResponse | None = None

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.answered = False
        self.transient_error = None
        self.last_response = None
        try:
            response = self._inner.generate(request)
        except Exception as exc:  # noqa: BLE001 - classified by the test
            self.transient_error = exc
            raise
        self.answered = True
        self.last_response = response
        return response


def _provider_answered(provider: _ObservedProvider) -> bool:
    """Whether the last provider call returned text (a real model response)."""

    return (
        provider.answered
        and provider.last_response is not None
        and bool(provider.last_response.text)
    )


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    # A key file is the local convenience used by the repro scripts; it is never read
    # in CI, and the file is outside the repo.
    path = os.environ.get("GEMINI_API_KEY_FILE", "").strip()
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    return ""


@pytest.fixture(scope="module")
def observed_provider() -> _ObservedProvider:
    key = _api_key()
    if not key:
        pytest.skip("GEMINI_API_KEY is not set; live composition contract not exercised")
    settings = ModelSettings.from_env({**os.environ, "GEMINI_API_KEY": key})
    return _ObservedProvider(GeminiProvider(settings))


@pytest.fixture(scope="module")
def serving(observed_provider: _ObservedProvider) -> ModelServing:
    settings = ModelSettings.from_env({**os.environ, "GEMINI_API_KEY": _api_key()})
    return ModelServing(observed_provider, KeywordRetrievalIndex([]), settings=settings)


@pytest.mark.parametrize("task", sorted(_TASK_CONTEXTS))
def test_real_model_composes_a_valid_non_empty_stream(
    serving: ModelServing,
    observed_provider: _ObservedProvider,
    task: str,
) -> None:
    """Every composition task yields a real, catalog-valid, non-empty surface.

    The assertions mirror the pre-send validator: the stream must be non-empty, must
    validate against the negotiated catalog, and must be marked ``source: model``.
    A fallback after an answered provider call is a failure on purpose: it is the
    degradation a broken prompt or schema would produce silently in production.
    """

    context = _TASK_CONTEXTS[task]
    provider = observed_provider

    # Retry only a transient provider transport failure. A composition fallback on an
    # answered response is deterministic, so it breaks out immediately and is reported
    # as a regression below.
    outcome = None
    for _attempt in range(_TRANSIENT_ATTEMPTS):
        outcome = serving.compose_surface(task, context, catalog_id=_CATALOG.catalog_id)
        if _provider_answered(provider):
            break

    if not _provider_answered(provider):
        cause = provider.transient_error
        if cause is not None:
            root = cause.__cause__ or cause
            detail = f"{type(root).__name__}: {root}"
        else:
            detail = "the provider returned no text"
        pytest.skip(f"{task}: the provider failed on {_TRANSIENT_ATTEMPTS} attempts ({detail})")

    assert outcome is not None and outcome.source == MODEL_SOURCE, (
        f"{task}: the model did not compose (source={outcome.source if outcome else None!r}, "
        f"used_fallback={outcome.used_fallback if outcome else None}); the provider answered "
        f"with {len(provider.last_response.text)} chars, so this is a composition regression"
    )
    assert outcome.used_fallback is False, f"{task}: composition degraded to a fallback"
    assert outcome.model_id == FLASH_MODEL_ID
    assert len(outcome.messages) > 0, f"{task}: the model returned an empty stream"

    validation = validate_a2ui_stream({"messages": list(outcome.messages)}, catalog=_CATALOG)
    assert validation.ok, f"{task}: composed stream failed catalog validation: {validation.errors}"
    assert validation.surface_id is not None, f"{task}: the stream creates no surface"
    assert validation.component_names, f"{task}: the stream defines no components"
