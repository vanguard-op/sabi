"""Fixtures for the AI-service integration and acceptance tests.

Run in a process where only ``services/ai`` is on ``sys.path`` (the AI service and
the API service each expose a top-level ``app`` package). The model is replaced with
a deterministic double per capability, so a run is offline and reproducible while
still exercising the real app, routers, validation, grounding, and fallback.

Reference: CONTRACTS.md C-009/C-010/C-012, model-quality.md.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
_AI_ROOT = _ROOT / "services" / "ai"
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))

from core.retrieval import KeywordRetrievalIndex, RetrievedRecord  # noqa: E402
from core.testing import FakeCandidate, FakeModelProvider  # noqa: E402


def _record(
    service_id: str,
    name: str,
    collecting_body: str,
    category: str,
    *,
    known_amount: int | None = None,
    aliases: tuple[str, ...] = (),
) -> RetrievedRecord:
    return FakeCandidate(
        service_id=service_id,
        name=name,
        collecting_body=collecting_body,
        category=category,
        known_amount=known_amount,
        aliases=aliases,
    ).to_record()


@pytest.fixture
def catalogue_records() -> list[RetrievedRecord]:
    return [
        _record(
            "svc-electric",
            "Ikeja Electric",
            "Ikeja Electricity Distribution Company",
            "electricity",
            known_amount=1_200_000,
            aliases=("electricity", "power", "light"),
        ),
        _record(
            "svc-landuse",
            "Land Use Charge",
            "Lagos State Government",
            "government",
            known_amount=2_500_000,
            aliases=("land use", "levy"),
        ),
    ]


@pytest.fixture
def retrieval_index(catalogue_records: list[RetrievedRecord]) -> KeywordRetrievalIndex:
    return KeywordRetrievalIndex(catalogue_records)


@pytest.fixture
def intent_service(retrieval_index: KeywordRetrievalIndex):
    from core.serving import ModelServing
    from intent.service import IntentService

    provider = FakeModelProvider()
    return IntentService(ModelServing(provider, retrieval_index)), provider


@pytest.fixture
def ranking_service(retrieval_index: KeywordRetrievalIndex):
    from core.serving import ModelServing
    from ranking.service import RankingService

    provider = FakeModelProvider()
    return RankingService(ModelServing(provider, retrieval_index)), provider


@pytest.fixture
def composition_serving():
    from composition.dependencies import build_serving
    from core.config import ModelSettings

    return build_serving(ModelSettings(api_key="test-key"), provider=_NullProvider())


class _NullProvider:
    """A provider that is always replaced before use."""

    def generate(self, request):  # pragma: no cover - overridden in every test
        from core.errors import ProviderUnavailable

        raise ProviderUnavailable("no response configured")


def scripted(responses):
    """A fake provider replaying responses in order (or raising exceptions)."""

    return FakeModelProvider(responses)


@pytest.fixture
def ai_client_factory():
    from contextlib import contextmanager

    from app.main import create_app
    from composition.dependencies import get_serving as get_composition_serving
    from intent.deps import get_intent_service
    from ranking.deps import get_ranking_service

    @contextmanager
    def build(*, intent=None, ranking=None, composition=None) -> Iterator[TestClient]:
        app = create_app()
        if intent is not None:
            app.dependency_overrides[get_intent_service] = lambda: intent
        if ranking is not None:
            app.dependency_overrides[get_ranking_service] = lambda: ranking
        if composition is not None:
            app.dependency_overrides[get_composition_serving] = lambda: composition
        with TestClient(app) as client:
            yield client

    return build
