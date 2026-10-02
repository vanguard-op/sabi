"""Catalogue discovery endpoints (C-010, C-011).

Search returns ranked, structured service records with the collecting body and
any known amount, and a ``noMatch`` flag the client uses to offer human
support. A miss is recorded for coverage planning; the catalogue never
fabricates a service (FEAT-004).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_rate_limiter
from app.catalogue import repository
from app.catalogue.misses import record_miss
from app.catalogue.schemas import (
    SearchResponse,
    ServiceResponse,
    ServiceSummary,
    serialize_service,
)
from app.catalogue.search import rank
from app.core.errors import APIError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData
from app.db.session import get_db

# Discovery returns at most five results (C-010); the query is bounded so a
# pathological input cannot become a scan or a log amplification.
_MIN_LIMIT = 1
_MAX_LIMIT = 5
_DEFAULT_LIMIT = 5
_MAX_QUERY_LENGTH = 200

router = APIRouter(tags=["catalogue"])

# Module-level dependency singletons keep the FastAPI idiom out of argument
# defaults (B008) while injecting the same callables.
_current_user = Depends(current_user)
_db_session = Depends(get_db)
_rate_limiter = Depends(get_rate_limiter)


@router.get("/catalogue/search", response_model=SearchResponse)
def search_catalogue(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    session: SessionData = _current_user,
    db: Session = _db_session,
    limiter: RateLimiter = _rate_limiter,
) -> SearchResponse:
    # Limit before validation so a burst of malformed requests cannot outrun it.
    limiter.check(f"catalogue:search:{session.user_id}")

    query = (q or "").strip()
    if not query:
        # Missing or blank q is a 400, not a validation 422 (C-010).
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter a service to search for.")
    if len(query) > _MAX_QUERY_LENGTH:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That search is too long.")

    effective_limit = max(_MIN_LIMIT, min(limit, _MAX_LIMIT))
    matches = rank(repository.candidates(db, category), query, effective_limit)

    if not matches:
        # Record the query for coverage planning; a miss is never turned into a
        # fabricated result (FEAT-004).
        record_miss(query, category)
        return SearchResponse(results=[], noMatch=True)

    results = [
        ServiceSummary(
            serviceId=service.id,
            name=service.name,
            collectingBody=service.collecting_body,
            category=service.category,
            knownAmount=service.known_amount,
            currency=service.currency,
            status=service.status,
            confidence=round(confidence, 4),
        )
        for service, confidence in matches
    ]
    return SearchResponse(results=results, noMatch=False)


@router.get("/catalogue/services/{serviceId}", response_model=ServiceResponse)
def get_catalogue_service(
    serviceId: str,
    session: SessionData = _current_user,
    db: Session = _db_session,
) -> ServiceResponse:
    service = repository.get(db, serviceId)
    if service is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "We could not find that service.")
    return ServiceResponse(service=serialize_service(service))
