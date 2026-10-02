"""Liveness endpoints. They answer without touching a dependency or the model."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
