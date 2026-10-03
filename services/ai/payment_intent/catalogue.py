"""Payment-intent extraction's retrieval seam, backed by the one shared registry.

The facts a payment intent is grounded in never come from a private index: the module
resolves the service's single process-wide registry at call time, so the catalogue
owner installs an index once and every model-backed feature grounds through it (see
:mod:`app.retrieval`). This module keeps the stable ``payment_intent.catalogue`` import
path the service and its tests use, and re-exports the shared registry rather than
holding a private copy.
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
