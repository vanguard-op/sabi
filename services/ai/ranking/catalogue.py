"""Discovery ranking's retrieval seam, backed by the one shared registry.

Discovery ranking never supplies its own facts: it selects from catalogue records
the retrieval index hands it (model-quality.md, "Grounding, safety, and refusal
behavior"). The registry itself lives in :mod:`app.retrieval` so intent resolution,
discovery ranking, and interface composition all ground through the same
process-wide index.

This module keeps the stable ``ranking.catalogue`` import path the feature and its
tests use, and re-exports the shared registry rather than holding a private copy.
"""

from __future__ import annotations

from app.retrieval import (
    LateBoundRetrievalIndex,
    get_retrieval_index,
    index_from_services,
    reset_retrieval_index,
    set_retrieval_index,
)

__all__ = [
    "LateBoundRetrievalIndex",
    "get_retrieval_index",
    "index_from_services",
    "reset_retrieval_index",
    "set_retrieval_index",
]
