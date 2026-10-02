"""Intent resolution's retrieval seam, backed by the one shared registry.

Intent resolution never supplies its own facts: target, amount, and reference come
from catalogue records the retrieval index hands the model (model-quality.md,
"Grounding, safety, and refusal behavior"). The registry itself lives in
:mod:`app.retrieval` so intent resolution, discovery ranking, and interface
composition all ground through the same process-wide index.

This module keeps the stable ``intent.catalogue`` import path the feature and its
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
