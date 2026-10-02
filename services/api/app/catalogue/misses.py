"""Coverage-planning record for catalogue queries that matched nothing.

A miss is evidence of demand the catalogue cannot yet serve, so the query is
recorded for coverage planning (FEAT-004). It is deliberately not attributed to
a user: analytics reference a user id only and never free text, and this record
exists to find gaps, not to profile anyone (architecture.md).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sabi.catalogue")

_MAX_RECORDED_QUERY = 200


def record_miss(query: str, category: str | None = None) -> None:
    logger.info(
        "catalogue search miss",
        extra={
            "catalogue_query": query[:_MAX_RECORDED_QUERY],
            "catalogue_category": category,
        },
    )
