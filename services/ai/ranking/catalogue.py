"""The retrieval seam discovery ranking reads from.

Discovery ranking never supplies its own facts: it selects from catalogue records
the retrieval index hands it (model-quality.md, "Grounding, safety, and refusal
behavior"). In production the index is the pgvector nearest-neighbour index over
catalogue content, wired at startup by the catalogue owner. This module holds the
single process-wide reference so the model-serving layer depends on a stable seam
instead of importing the catalogue's database code.

The default is an empty lexical index, so the service boots and answers
``no_match`` before the catalogue is wired rather than fabricating a result. The
lexical index here is deterministic and dependency-free and is also what tests
seed; it ranks on the same names, aliases, collecting bodies, and categories the
catalogue exposes.
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

    The model-serving layer is built once, while the catalogue index is installed
    later at startup; binding late keeps both orderings correct.
    """

    def search(self, query: str, *, limit: int) -> list[RetrievedRecord]:
        return list(get_retrieval_index().search(query, limit=limit))


def index_from_services(services: Iterable[Mapping[str, Any]]) -> KeywordRetrievalIndex:
    """Build a deterministic lexical index from catalogue service payloads.

    The payload keys are the catalogue's own (``service_id``, ``name``,
    ``collecting_body``, ``category``, ``aliases``, ``known_amount``, ...). A
    payload without an identifier is skipped: a record that cannot be cited is
    not a record.
    """

    records: list[RetrievedRecord] = []
    for service in services:
        try:
            records.append(RetrievedRecord.from_service(service))
        except ValueError:
            continue
    return KeywordRetrievalIndex(records)
