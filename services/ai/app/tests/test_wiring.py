"""Service wiring: one shared retrieval registry and a fail-closed provider.

These protect the wiring the model-backed features depend on, with the model mocked
so the suite stays deterministic:

* every feature package grounds through the single registry in :mod:`app.retrieval`,
  so an index installed once serves intent resolution, discovery ranking, and
  interface composition;
* every feature's provider wrapper turns a client-construction failure into a
  provider failure, so the documented keyword fallback runs instead of a 500;
* the service entrypoint mounts all three frozen feature contracts under ``/v1``
  and imports cleanly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.provider import FailClosedProvider
from app.retrieval import (
    LateBoundRetrievalIndex,
    reset_retrieval_index,
    set_retrieval_index,
)
from core.errors import ProviderUnavailable
from core.testing import FakeCandidate, index_over


class _ExplodingProvider:
    """A provider whose client construction fails before any model call."""

    def generate(self, request: object) -> object:
        raise ValueError("No API key was provided.")


def test_intent_and_ranking_share_one_registry() -> None:
    import intent.catalogue as intent_catalogue
    import ranking.catalogue as ranking_catalogue

    catalogue = index_over([])
    set_retrieval_index(catalogue)
    try:
        assert intent_catalogue.get_retrieval_index() is catalogue
        assert ranking_catalogue.get_retrieval_index() is catalogue
    finally:
        reset_retrieval_index()


def test_late_bound_index_reads_the_shared_registry() -> None:
    catalogue = index_over(
        [
            FakeCandidate(
                service_id="svc-electric",
                name="Ikeja Electric",
                collecting_body="Ikeja Electricity Distribution Company",
                category="electricity",
                aliases=("electricity", "power"),
            )
        ]
    )
    set_retrieval_index(catalogue)
    try:
        # A late-bound index resolves the registry per call, so the catalogue owner
        # can install the index after the feature serving layers were built.
        hits = LateBoundRetrievalIndex().search("electricity", limit=5)
        assert [record.service_id for record in hits] == ["svc-electric"]
        reset_retrieval_index()
        assert LateBoundRetrievalIndex().search("electricity", limit=5) == []
    finally:
        reset_retrieval_index()


def test_fail_closed_provider_degrades_a_construction_error() -> None:
    wrapped = FailClosedProvider(_ExplodingProvider())
    with pytest.raises(ProviderUnavailable):
        wrapped.generate(None)


def test_fail_closed_provider_preserves_a_model_error() -> None:
    class _Unavailable:
        def generate(self, request: object) -> object:
            raise ProviderUnavailable("down")

    with pytest.raises(ProviderUnavailable):
        FailClosedProvider(_Unavailable()).generate(None)


def test_every_feature_builder_wraps_its_provider_fail_closed() -> None:
    from composition.dependencies import build_serving
    from intent.deps import build_intent_service
    from ranking.deps import build_ranking_service

    # The production builders must not hand a bare provider to the serving layer, or
    # a client-construction error would escape as a 500 instead of the fallback.
    intent_serving = build_intent_service()._serving  # noqa: SLF001
    ranking_serving = build_ranking_service()._serving  # noqa: SLF001
    composition_serving = build_serving()
    for serving in (intent_serving, ranking_serving, composition_serving):
        assert isinstance(serving._provider, FailClosedProvider)  # noqa: SLF001


def test_all_frozen_feature_contracts_are_mounted_under_v1() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/v1/agent/intents" in paths
    assert "/v1/catalogue/search" in paths
    assert "/v1/agent/surfaces" in paths


def test_private_surface_documents_the_gateway_position() -> None:
    app = create_app()
    description = app.description
    assert "gateway" in description.lower()
    for contract in ("C-009", "C-010", "C-012"):
        assert contract in description


def test_create_app_imports_and_answers_health() -> None:
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
