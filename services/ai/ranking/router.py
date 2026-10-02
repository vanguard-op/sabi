"""Discovery search endpoint (C-010, FEAT-004).

Serves the model-backed ranking as the C-010 ``ServiceSummary`` list. The model
selects from catalogue records and never invents a service or a collecting body;
a request the model cannot use degrades to keyword search with the same rule, and
a query that matches nothing returns ``noMatch`` and is recorded for coverage.

Auth and rate limiting are gateway concerns (architecture.md, "API Gateway /
Backend-for-Frontend"); this is the internal model-serving surface behind them,
so it validates the query and returns the C-010 body.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from core.config import MAX_RESULTS
from ranking.deps import get_ranking_service
from ranking.schemas import SearchResponse, error_body
from ranking.service import RankingService

# C-010 bounds: a non-empty query of at most 200 characters, and at most five
# results. The query is bounded so a pathological input cannot become a scan, and
# the limit is clamped rather than rejected, matching the catalogue surface.
_MIN_LIMIT = 1
_MAX_LIMIT = MAX_RESULTS
_DEFAULT_LIMIT = MAX_RESULTS
_MAX_QUERY_LENGTH = 200

_INVALID_REQUEST = "invalid_request"

router = APIRouter(tags=["catalogue"])

# Module-level dependency singleton keeps the FastAPI idiom out of argument defaults
# (B008), matching the catalogue surface in the API service.
_ranking_service = Depends(get_ranking_service)


@router.get("/catalogue/search", response_model=SearchResponse)
def search_catalogue(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    service: RankingService = _ranking_service,
) -> SearchResponse | JSONResponse:
    query = (q or "").strip()
    if not query:
        # Missing or blank q is a 400, not a validation 422 (C-010).
        return JSONResponse(
            status_code=400,
            content=error_body(_INVALID_REQUEST, "Enter a service to search for."),
        )
    if len(query) > _MAX_QUERY_LENGTH:
        return JSONResponse(
            status_code=400,
            content=error_body(_INVALID_REQUEST, "That search is too long."),
        )

    effective_limit = max(_MIN_LIMIT, min(limit, _MAX_LIMIT))
    result = service.search(query, category=category, limit=effective_limit)
    return result.response
