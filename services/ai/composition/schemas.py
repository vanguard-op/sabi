"""Request and response models for the composed task surface (C-012).

The wire fields are camelCase (DELIVERY.md conventions; D-018). The request is
validated with Pydantic so FastAPI returns its standard 422 for a body that is
not an object or is missing ``task``/``context``; the handler itself decides what
is a supported task and what falls back.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SurfaceRequest(BaseModel):
    """A request for a task surface.

    ``context`` is untrusted, free-form task context (for example the amount and
    payee of a confirmation). It is serialised into the prompt as data and can
    never change the composition rules.
    """

    model_config = ConfigDict(extra="ignore")

    task: str
    context: dict[str, Any] = Field(default_factory=dict)


class SurfaceResponse(BaseModel):
    """The declarative UI stream and the fallback task key.

    ``messages`` is empty exactly when composition failed and the client must
    render its static fallback form for ``fallback``. The stream is already
    validated against the client component catalogue before it reaches here.
    """

    messages: list[dict[str, Any]]
    fallback: str
