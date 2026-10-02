"""Intent resolution feature package (FEAT-003, MQ-001).

Exposes the C-009 HTTP adapter over the model-serving foundation. The package is
auto-discovered and its router mounted at ``/v1`` by :mod:`app.main`; a capability
that cannot answer degrades to keyword and search resolution with mandatory
confirmation (model-quality.md, MQ-001 Fallback).
"""

from __future__ import annotations
