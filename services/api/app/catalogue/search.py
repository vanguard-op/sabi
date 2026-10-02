"""Deterministic relevance ranking for catalogue search.

Index-free scoring so discovery works the same on the primary store in every
environment and is unit-testable without a database. A query matches the
current name, the former names (aliases), the collecting body, and the
category; a renamed agency is found by its old name but still returned under
its current registered name (FEAT-004).

The repository supplies candidates; this module is pure and holds the scoring
rules. When the catalogue outgrows an in-process scan, the same rule set can be
pushed behind the primary store's full-text index (architecture.md, Service
Catalogue and Search).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

_TOKEN_SPLIT = re.compile(r"[^\w]+", re.UNICODE)

# A name match outranks a collecting-body or category match; an alias is a
# former name, so it ranks just below the current one.
_FIELD_WEIGHTS: dict[str, float] = {
    "name": 1.0,
    "aliases": 0.9,
    "collecting_body": 0.8,
    "category": 0.7,
}

_EXACT = 1.0
_SUBSTRING = 0.9
_CONTAINED = 0.85
_TOKEN = 0.65


def tokenize(query: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT.split(query.casefold()) if token]


def _field_ratio(text: str, query: str, tokens: Sequence[str]) -> float:
    normalized = text.casefold()
    if normalized == query:
        return _EXACT
    if query and query in normalized:
        return _SUBSTRING
    if normalized and normalized in query:
        return _CONTAINED
    if not tokens:
        return 0.0
    matched = sum(1 for token in tokens if token in normalized)
    return _TOKEN * matched / len(tokens)


def score_service(service: Any, query: str) -> float:
    """Score one service against a query in the closed range 0.0 to 1.0."""
    normalized = query.casefold().strip()
    tokens = tokenize(normalized)
    if not tokens:
        return 0.0

    best = 0.0
    for field, weight in _FIELD_WEIGHTS.items():
        if field == "aliases":
            continue
        text = getattr(service, field, "") or ""
        best = max(best, _field_ratio(str(text), normalized, tokens) * weight)

    for alias in getattr(service, "aliases", None) or []:
        best = max(best, _field_ratio(str(alias), normalized, tokens) * _FIELD_WEIGHTS["aliases"])

    return min(best, 1.0)


def rank(services: Sequence[Any], query: str, limit: int) -> list[tuple[Any, float]]:
    """Return the highest-scoring services, strongest first, capped at ``limit``."""
    scored = [(service, score_service(service, query)) for service in services]
    matches = [pair for pair in scored if pair[1] > 0.0]
    matches.sort(key=lambda pair: (-pair[1], str(getattr(pair[0], "name", "")).casefold()))
    return matches[:limit]
