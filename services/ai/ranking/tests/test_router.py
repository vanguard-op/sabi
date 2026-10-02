"""HTTP conformance tests for discovery ranking (C-010).

The model is a deterministic double injected through FastAPI's dependency
override, so no network call or SDK is involved.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.serving import ModelServing
from core.testing import FakeModelProvider, json_response, text_response
from ranking.deps import get_ranking_service
from ranking.schemas import SearchResponse
from ranking.service import RankingSearch, RankingService


def _service_payload(service_id: str = "svc-electric", confidence: float = 0.9) -> dict:
    return {
        "service_id": service_id,
        "name": "Ikeja Electric",
        "collecting_body": "Ikeja Electricity Distribution Company",
        "category": "electricity",
        "known_amount": 1200000,
        "currency": "NGN",
        "status": "active",
        "confidence": confidence,
    }


@contextmanager
def _client(service) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_ranking_service] = lambda: service
    with TestClient(app) as client:
        yield client


def _service_for(catalogue, responses) -> RankingService:
    return RankingService(ModelServing(FakeModelProvider(responses), catalogue))


def test_search_returns_the_c010_body(catalogue):
    payload = {"results": [_service_payload()], "no_match": False}
    client = _service_for(catalogue, [json_response(payload)])
    with _client(client) as http:
        response = http.get("/v1/catalogue/search", params={"q": "electricity"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"results", "noMatch"}
    assert body["noMatch"] is False
    first = body["results"][0]
    assert set(first) == {
        "serviceId",
        "name",
        "collectingBody",
        "category",
        "knownAmount",
        "currency",
        "status",
        "confidence",
    }
    assert first["serviceId"] == "svc-electric"


def test_search_no_match_body(catalogue):
    client = _service_for(catalogue, [json_response({"results": [], "no_match": True})])
    with _client(client) as http:
        response = http.get("/v1/catalogue/search", params={"q": "crypto exchange"})

    assert response.status_code == 200
    assert response.json() == {"results": [], "noMatch": True}


def test_search_falls_back_within_the_contract_body(catalogue):
    client = _service_for(catalogue, [text_response("not json")])
    with _client(client) as http:
        response = http.get("/v1/catalogue/search", params={"q": "electricity"})

    assert response.status_code == 200
    body = response.json()
    assert body["noMatch"] is False
    assert [item["serviceId"] for item in body["results"]] == ["svc-electric"]
    assert body["results"][0]["confidence"] == 0.0


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}])
def test_missing_or_blank_query_is_a_400_envelope(catalogue, params):
    provider = FakeModelProvider([])
    client = RankingService(ModelServing(provider, catalogue))
    with _client(client) as http:
        response = http.get("/v1/catalogue/search", params=params)

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_request"
    # Nothing reaches the model for a query that cannot be searched.
    assert provider.requests == []


def test_over_length_query_is_a_400_envelope(catalogue):
    provider = FakeModelProvider([])
    client = RankingService(ModelServing(provider, catalogue))
    with _client(client) as http:
        response = http.get("/v1/catalogue/search", params={"q": "x" * 201})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert provider.requests == []


class _LimitCapturingService:
    """A service double that records the clamped limit the router passes down."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, str | None, int]] = []

    def search(self, query: str, *, category: str | None = None, limit: int = 5) -> RankingSearch:
        self.seen.append((query, category, limit))
        return RankingSearch(
            response=SearchResponse(results=[], noMatch=True),
            source="model",
            used_fallback=False,
            citations=(),
        )


def test_limit_is_clamped_to_the_contract_bounds():
    fake = _LimitCapturingService()
    with _client(fake) as http:
        assert http.get("/v1/catalogue/search", params={"q": "a", "limit": 99}).status_code == 200
        assert http.get("/v1/catalogue/search", params={"q": "a", "limit": 0}).status_code == 200
        assert http.get("/v1/catalogue/search", params={"q": "a"}).status_code == 200

    assert [limit for _, _, limit in fake.seen] == [5, 1, 5]
    assert fake.seen[1] == ("a", None, 1)


def test_category_is_passed_through_to_the_model(catalogue):
    provider = FakeModelProvider([json_response({"results": [], "no_match": True})])
    client = RankingService(ModelServing(provider, catalogue))
    with _client(client) as http:
        response = http.get("/v1/catalogue/search", params={"q": "levy", "category": "government"})

    assert response.status_code == 200
    assert "government" in provider.last_request.contents
