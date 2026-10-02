"""The one shared retrieval registry the feature packages ground against.

Intent resolution (C-009) and discovery ranking (C-010) both ground their output in
Sabi's own catalogue records; interface composition (C-012) is grounded in the task
context it receives, but it binds the same registry so every model-backed feature is
wired through one process-wide seam. This module owns that single registry.

In production the installed index is the pgvector nearest-neighbour index over
catalogue content, installed once at startup by the catalogue owner. Until it is
wired the default is an empty lexical index, so the service boots and degrades to the
documented keyword fallback rather than letting an ungrounded fact through.

Keeping the registry here, in the service entrypoint package, means no feature
package owns a private copy: an index installed once serves every capability.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.retrieval import KeywordRetrievalIndex, RetrievalIndex, RetrievedRecord

_EMPTY_INDEX: KeywordRetrievalIndex = KeywordRetrievalIndex([])
_index: RetrievalIndex = _EMPTY_INDEX


def set_retrieval_index(index: RetrievalIndex) -> None:
    """Install the process-wide retrieval index. Called once by the catalogue owner."""

    global _index
    _index = index


def reset_retrieval_index() -> None:
    """Restore the empty default. Used by tests so each case starts clean."""

    global _index
    _index = _EMPTY_INDEX


def get_retrieval_index() -> RetrievalIndex:
    """The current retrieval index. Never ``None``; defaults to empty."""

    return _index


class LateBoundRetrievalIndex:
    """A :class:`~core.retrieval.RetrievalIndex` that resolves the registry per call.

    The serving layer for each feature is built once, while the catalogue index is
    installed later at startup; binding late keeps both orderings correct and lets
    every feature see the same installed index.
    """

    def search(self, query: str, *, limit: int) -> list[RetrievedRecord]:
        return list(get_retrieval_index().search(query, limit=limit))


def index_from_services(services: Iterable[Mapping[str, Any]]) -> KeywordRetrievalIndex:
    """Build a deterministic lexical index from catalogue service payloads.

    A payload without an identifier is skipped: a record that cannot be cited is not a
    record.
    """

    records: list[RetrievedRecord] = []
    for service in services:
        try:
            records.append(RetrievedRecord.from_service(service))
        except ValueError:
            continue
    return KeywordRetrievalIndex(records)
