"""Discovery ranking service (MQ-002, C-010).

The service is a thin adapter over :class:`~core.serving.ModelServing`:

* it retrieves candidate records, lets the pinned model rank them, grounds the
  result against the retrieved set, and returns the C-010 shape;
* when the provider is unavailable or its output is unusable, ``ModelServing``
  degrades to non-model keyword search over catalogue names and aliases, with the
  same no-invention rule (model-quality.md, MQ-002 Fallback);
* when nothing clears the ranking threshold it reports ``no_match`` and records
  the query for coverage planning, exactly as FEAT-004 requires. It never
  fabricates a service or a collecting body.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.config import MAX_RESULTS
from core.serving import ModelServing, RankingOutcome
from ranking.schemas import SearchResponse

logger = logging.getLogger("ranking.service")

# A miss is coverage evidence, not a profile: the catalogue records the query text
# so demand the catalogue cannot yet serve is visible. The query is truncated to
# bound log amplification and is never attributed to a user (FEAT-004).
_MAX_RECORDED_QUERY = 200


@dataclass(frozen=True)
class RankingSearch:
    """One discovery search, ready to render as the C-010 body."""

    response: SearchResponse
    source: str
    used_fallback: bool
    citations: tuple[str, ...]


class RankingService:
    """Ranks catalogue records for a discovery query."""

    def __init__(self, serving: ModelServing) -> None:
        self._serving = serving

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = MAX_RESULTS,
    ) -> RankingSearch:
        outcome: RankingOutcome = self._serving.rank_services(query, category=category, limit=limit)
        if outcome.no_match and not outcome.results:
            self._record_miss(query, category)
        return RankingSearch(
            response=SearchResponse.from_outcome(outcome),
            source=outcome.source,
            used_fallback=outcome.used_fallback,
            citations=outcome.citations,
        )

    @staticmethod
    def _record_miss(query: str, category: str | None) -> None:
        logger.info(
            "ranking no_match",
            extra={
                "catalogue_query": query[:_MAX_RECORDED_QUERY],
                "catalogue_category": category,
            },
        )
