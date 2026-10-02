"""Wire models for discovery ranking (C-010).

Wire fields are camelCase (D-018); the model's internal schema stays snake_case and
is mapped here at the boundary. The field set and nullability match C-010
``ServiceSummary`` exactly, so the client and the API can consume this response
without reshaping it.
"""

from __future__ import annotations

from pydantic import BaseModel

from core.serving import RankingOutcome


class ServiceSummaryOut(BaseModel):
    """One ranked discovery result (C-010)."""

    serviceId: str
    name: str
    collectingBody: str
    category: str
    knownAmount: int | None
    currency: str
    status: str
    confidence: float


class SearchResponse(BaseModel):
    """The C-010 response body."""

    results: list[ServiceSummaryOut]
    noMatch: bool

    @classmethod
    def from_outcome(cls, outcome: RankingOutcome) -> SearchResponse:
        return cls(
            results=[
                ServiceSummaryOut(
                    serviceId=item.service_id,
                    name=item.name,
                    collectingBody=item.collecting_body,
                    category=item.category,
                    knownAmount=item.known_amount,
                    currency=item.currency,
                    status=item.status,
                    confidence=item.confidence,
                )
                for item in outcome.results
            ],
            noMatch=outcome.no_match,
        )


def error_body(code: str, message: str) -> dict:
    """The shared error envelope (DELIVERY.md, conventions)."""

    return {"error": {"code": code, "message": message}}
