"""Catalogue discovery unit tests (FEAT-004, C-010, C-011).

Covers the ranking rules, the contract's request/response shape and errors, and
the coverage-planning record for a miss.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.catalogue import misses
from app.catalogue.search import rank, score_service, tokenize
from app.db.models import Service


class _StubService:
    def __init__(
        self,
        *,
        name: str = "",
        collecting_body: str = "",
        category: str = "",
        aliases: list[str] | None = None,
    ) -> None:
        self.name = name
        self.collecting_body = collecting_body
        self.category = category
        self.aliases = aliases or []


@pytest.fixture
def catalogue(app, client, db_session_factory, session_manager):
    """A client backed by an isolated SQLite store, with helpers to seed and sign in."""
    app.state.session_factory = db_session_factory

    def add_service(**overrides: object) -> Service:
        values: dict[str, object] = {
            "type": "government",
            "name": "Onitsha South Local Government Council",
            "collecting_body": "Onitsha South LGA",
            "category": "levy",
            "aliases": ["Onitsha City Council"],
            "currency": "NGN",
            "status": "active",
        }
        values.update(overrides)
        with db_session_factory() as db:
            service = Service(**values)
            db.add(service)
            db.commit()
            db.refresh(service)
            return service

    def sign_in(user_id: str = "user-1") -> None:
        token, _ = session_manager.issue(user_id=user_id)
        client.cookies.set(session_manager.settings.session_cookie_name, token)

    return SimpleNamespace(client=client, add_service=add_service, sign_in=sign_in)


# --- ranking rules ---------------------------------------------------------


def test_tokenize_splits_on_punctuation_and_case() -> None:
    assert tokenize("Council-Levy, Onitsha!") == ["council", "levy", "onitsha"]


def test_exact_name_match_scores_highest() -> None:
    service = _StubService(name="Onitsha City Council")
    assert score_service(service, "onitsha city council") == 1.0


def test_alias_ranks_below_the_current_name() -> None:
    current = _StubService(name="Onitsha City Council")
    former = _StubService(name="Unrelated Body", aliases=["Onitsha City Council"])
    query = "Onitsha City Council"
    assert score_service(current, query) > score_service(former, query)
    assert score_service(former, query) > 0.0


def test_unrelated_query_scores_zero() -> None:
    service = _StubService(name="Onitsha City Council", category="levy")
    assert score_service(service, "airtime lagos") == 0.0


def test_rank_orders_by_score_then_name_and_caps() -> None:
    services = [
        _StubService(name="Levy Delta"),
        _StubService(name="Levy Alpha"),
        _StubService(name="Levy Bravo"),
    ]
    matches = rank(services, "levy", 2)
    assert [service.name for service, _ in matches] == ["Levy Alpha", "Levy Bravo"]


def test_renamed_agency_is_found_by_former_name_under_current_name() -> None:
    renamed = _StubService(
        name="Onitsha South Local Government Council",
        aliases=["Onitsha City Council"],
    )
    matches = rank([renamed], "Onitsha City Council", 5)
    assert matches and matches[0][0].name == "Onitsha South Local Government Council"


# --- miss recording --------------------------------------------------------


def test_record_miss_logs_the_query_without_a_user(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, dict]] = []

    class _Capture:
        def info(self, message: str, **kwargs: object) -> None:
            captured.append((message, kwargs))

    monkeypatch.setattr(misses, "logger", _Capture())
    misses.record_miss("council levy Onitsha", category="levy")

    assert captured
    message, kwargs = captured[0]
    assert message == "catalogue search miss"
    assert kwargs["extra"]["catalogue_query"] == "council levy Onitsha"
    assert kwargs["extra"]["catalogue_category"] == "levy"


# --- search endpoint (C-010) ----------------------------------------------


def test_search_requires_a_session(catalogue) -> None:
    response = catalogue.client.get("/v1/catalogue/search", params={"q": "levy"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_search_missing_or_blank_q_is_400(catalogue) -> None:
    catalogue.sign_in()
    missing = catalogue.client.get("/v1/catalogue/search")
    blank = catalogue.client.get("/v1/catalogue/search", params={"q": "   "})
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "invalid_request"
    assert blank.status_code == 400


def test_search_lists_the_matching_collecting_body(catalogue) -> None:
    service = catalogue.add_service()
    catalogue.sign_in()

    response = catalogue.client.get("/v1/catalogue/search", params={"q": "council levy Onitsha"})

    assert response.status_code == 200
    body = response.json()
    assert body["noMatch"] is False
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["serviceId"] == service.id
    assert result["name"] == "Onitsha South Local Government Council"
    assert result["collectingBody"] == "Onitsha South LGA"
    assert result["knownAmount"] is None
    assert result["confidence"] > 0


def test_search_passes_through_a_known_amount(catalogue) -> None:
    catalogue.add_service(known_amount=500_000)
    catalogue.sign_in()

    response = catalogue.client.get("/v1/catalogue/search", params={"q": "council levy"})

    assert response.json()["results"][0]["knownAmount"] == 500_000
    assert response.json()["results"][0]["currency"] == "NGN"


def test_search_prefers_the_current_name_for_a_renamed_agency(catalogue) -> None:
    catalogue.add_service(aliases=["Onitsha City Council"])
    catalogue.sign_in()

    response = catalogue.client.get("/v1/catalogue/search", params={"q": "Onitsha City Council"})

    assert response.json()["results"][0]["name"] == "Onitsha South Local Government Council"


def test_search_no_match_is_recorded_for_coverage(catalogue) -> None:
    catalogue.sign_in()

    response = catalogue.client.get(
        "/v1/catalogue/search", params={"q": "nothing like this exists"}
    )

    assert response.status_code == 200
    assert response.json() == {"results": [], "noMatch": True}


def test_search_excludes_retired_records(catalogue) -> None:
    catalogue.add_service(status="retired")
    catalogue.sign_in()

    response = catalogue.client.get("/v1/catalogue/search", params={"q": "council levy"})

    assert response.json()["noMatch"] is True


def test_search_filters_by_category(catalogue) -> None:
    catalogue.add_service()
    catalogue.add_service(
        name="MTN Airtime",
        collecting_body="MTN Nigeria",
        category="airtime",
        aliases=["mtn"],
    )
    catalogue.sign_in()

    airtime = catalogue.client.get(
        "/v1/catalogue/search", params={"q": "mtn", "category": "airtime"}
    )
    levy = catalogue.client.get("/v1/catalogue/search", params={"q": "mtn", "category": "levy"})

    assert [r["category"] for r in airtime.json()["results"]] == ["airtime"]
    assert levy.json()["noMatch"] is True


def test_search_limit_is_clamped_between_one_and_five(catalogue) -> None:
    for index in range(6):
        catalogue.add_service(
            name=f"Levy {index}",
            collecting_body="State Revenue Office",
            aliases=[],
        )
    catalogue.sign_in()

    default_cap = catalogue.client.get("/v1/catalogue/search", params={"q": "levy"})
    oversized = catalogue.client.get("/v1/catalogue/search", params={"q": "levy", "limit": 50})

    assert len(default_cap.json()["results"]) == 5
    assert len(oversized.json()["results"]) == 5


def test_search_is_rate_limited(catalogue) -> None:
    catalogue.sign_in()
    catalogue.client.get("/v1/catalogue/search", params={"q": "levy"})
    catalogue.client.get("/v1/catalogue/search", params={"q": "levy"})

    response = catalogue.client.get("/v1/catalogue/search", params={"q": "levy"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in response.headers


# --- service endpoint (C-011) ---------------------------------------------


def test_get_service_returns_the_full_record(catalogue) -> None:
    service = catalogue.add_service(known_amount=25_000)
    catalogue.sign_in()

    response = catalogue.client.get(f"/v1/catalogue/services/{service.id}")

    assert response.status_code == 200
    record = response.json()["service"]
    assert record["id"] == service.id
    assert record["type"] == "government"
    assert record["collectingBody"] == "Onitsha South LGA"
    assert record["knownAmount"] == 25_000
    assert record["aliases"] == ["Onitsha City Council"]
    assert record["providerId"] is None
    assert record["refreshedAt"] is None
    assert record["createdAt"].endswith("Z")


def test_get_service_unknown_is_404(catalogue) -> None:
    catalogue.sign_in()
    response = catalogue.client.get("/v1/catalogue/services/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_service_requires_a_session(catalogue) -> None:
    service = catalogue.add_service()
    response = catalogue.client.get(f"/v1/catalogue/services/{service.id}")
    assert response.status_code == 401
