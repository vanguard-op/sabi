"""Unit tests for the discovery ranking service (MQ-002, C-010).

The model is a deterministic double. These cover the contract-relevant behavior:
grounding of model output, the no-match path, the keyword fallback with
no-invention, and the camelCase mapping the wire contract depends on.
"""

from __future__ import annotations

import logging

import pytest

from core.config import FLASH_MODEL_ID
from core.errors import ProviderUnavailable
from core.serving import ModelServing
from core.testing import FakeModelProvider, json_response, text_response
from ranking.catalogue import (
    LateBoundRetrievalIndex,
    index_from_services,
    reset_retrieval_index,
    set_retrieval_index,
)
from ranking.service import RankingService


def _serving(
    catalogue, responses=None, *, responder=None
) -> tuple[RankingService, FakeModelProvider]:
    provider = FakeModelProvider(responses, responder=responder)
    return RankingService(ModelServing(provider, catalogue)), provider


def _service(service_id: str = "svc-electric", confidence: float = 0.9) -> dict:
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


def test_search_maps_the_contract_shape(catalogue):
    payload = {"results": [_service(), _service("svc-landuse", 0.8)], "no_match": False}
    service, _ = _serving(catalogue, [json_response(payload)])

    # The query retrieves both services, so both are groundable.
    result = service.search("electricity land")

    assert result.source == "model"
    assert result.used_fallback is False
    assert result.citations == ("svc-electric", "svc-landuse")
    body = result.response.model_dump()
    assert body["noMatch"] is False
    assert [item["serviceId"] for item in body["results"]] == ["svc-electric", "svc-landuse"]
    first = body["results"][0]
    assert first["collectingBody"] == "Ikeja Electricity Distribution Company"
    assert first["knownAmount"] == 1200000
    assert first["confidence"] == 0.9
    # The wire model never leaks the internal snake_case keys.
    assert "service_id" not in first


def test_search_preserves_model_order(catalogue):
    payload = {
        "results": [_service("svc-landuse", 0.7), _service("svc-electric", 0.9)],
        "no_match": False,
    }
    service, _ = _serving(catalogue, [json_response(payload)])
    result = service.search("electricity land")
    assert [item.serviceId for item in result.response.results] == [
        "svc-landuse",
        "svc-electric",
    ]


def test_search_drops_a_fabricated_service(catalogue):
    payload = {"results": [_service("svc-ghost", 0.99)], "no_match": False}
    service, _ = _serving(catalogue, [json_response(payload)])

    result = service.search("electricity")

    assert result.response.noMatch is True
    assert result.response.results == []
    assert result.citations == ()


def test_search_filters_results_below_the_ranking_threshold(catalogue):
    payload = {"results": [_service("svc-electric", 0.1)], "no_match": False}
    service, _ = _serving(catalogue, [json_response(payload)])

    result = service.search("electricity")

    assert result.response.noMatch is True
    assert result.response.results == []


def test_search_reports_no_match_for_an_empty_model_answer(catalogue):
    service, _ = _serving(catalogue, [json_response({"results": [], "no_match": True})])
    result = service.search("airtime topup")
    assert result.response.noMatch is True
    assert result.response.results == []


def test_search_records_a_no_match_query(catalogue, caplog):
    service, _ = _serving(catalogue, [json_response({"results": [], "no_match": True})])
    with caplog.at_level(logging.INFO, logger="ranking.service"):
        service.search("crypto exchange")
    record = next(r for r in caplog.records if r.message == "ranking no_match")
    assert record.catalogue_query == "crypto exchange"


def test_search_does_not_record_a_query_that_matched(catalogue, caplog):
    service, _ = _serving(catalogue, [json_response({"results": [_service()], "no_match": False})])
    with caplog.at_level(logging.INFO, logger="ranking.service"):
        service.search("electricity")
    assert not any(r.message == "ranking no_match" for r in caplog.records)


def test_search_falls_back_to_keyword_search_on_provider_failure(catalogue):
    service, _ = _serving(catalogue, [ProviderUnavailable("down")])

    result = service.search("electricity")

    assert result.source == "fallback"
    assert result.used_fallback is True
    assert [item.serviceId for item in result.response.results] == ["svc-electric"]
    assert result.response.noMatch is False


def test_fallback_confidence_is_unconfirmed(catalogue):
    service, _ = _serving(catalogue, [ProviderUnavailable("down")])
    result = service.search("electricity")
    assert result.response.results[0].confidence == 0.0


def test_search_falls_back_on_unparseable_output(catalogue):
    service, _ = _serving(catalogue, [text_response("not json")])
    result = service.search("electricity")
    assert result.source == "fallback"
    assert [item.serviceId for item in result.response.results] == ["svc-electric"]


def test_search_accepts_a_no_match_fallback_without_hallucinating(catalogue):
    service, _ = _serving(catalogue, [ProviderUnavailable("down")])
    result = service.search("crypto exchange")
    assert result.response.noMatch is True
    assert result.response.results == []


def test_ranking_uses_the_pinned_flash_build_and_decoding(catalogue):
    service, provider = _serving(catalogue, [json_response({"results": [], "no_match": True})])
    service.search("electricity", category="electricity", limit=3)
    request = provider.last_request
    assert request.prompt_id == "discovery_ranking"
    assert request.prompt_version == "v1"
    assert request.model_id == FLASH_MODEL_ID
    assert request.decoding.temperature == 0.0
    assert request.decoding.top_p == 1.0
    assert "electricity" in request.contents
    assert "RETRIEVED_DATA" in request.contents


def test_search_passes_the_category_filter_into_the_prompt(catalogue):
    service, provider = _serving(catalogue, [json_response({"results": [], "no_match": True})])
    service.search("levy", category="government")
    assert "government" in provider.last_request.contents


def test_limit_bounds_the_returned_results(catalogue):
    payload = {
        "results": [_service("svc-electric", 0.9), _service("svc-landuse", 0.8)],
        "no_match": False,
    }
    service, _ = _serving(catalogue, [json_response(payload)])
    result = service.search("electricity land", limit=1)
    assert [item.serviceId for item in result.response.results] == ["svc-electric"]


@pytest.mark.parametrize("raw", ["", "   ", "electricity"])
def test_late_bound_index_uses_the_registry(catalogue, raw):
    # A late-bound index resolves the registry per call, so the catalogue owner can
    # install the index after the serving layer was built.
    set_retrieval_index(catalogue)
    try:
        index = LateBoundRetrievalIndex()
        assert index.search(raw, limit=5) == list(catalogue.search(raw, limit=5))
    finally:
        reset_retrieval_index()


def test_index_from_services_skips_records_without_an_identifier():
    index = index_from_services(
        [
            {"name": "No Id", "collecting_body": "Body", "category": "other"},
            {
                "service_id": "svc-ok",
                "name": "Good",
                "collecting_body": "Body",
                "category": "other",
            },
        ]
    )
    hits = index.search("good", limit=5)
    assert [record.service_id for record in hits] == ["svc-ok"]
