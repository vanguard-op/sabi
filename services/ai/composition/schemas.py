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

    ``catalogId`` is the client's published Sabi A2UI catalog, negotiated from the
    ``supportedCatalogIds`` the client advertises. It is passed to composition
    unchanged; an absent value is not compatible, so the agent sends no surface and
    the client renders its same-task fallback (C-012 revision 2).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    task: str
    context: dict[str, Any] = Field(default_factory=dict)
    catalog_id: str | None = Field(default=None, alias="catalogId")


class SurfaceResponse(BaseModel):
    """The A2UI message stream and the fallback task key.

    ``messages`` is the A2UI v0.9 stream conforming to the published catalog; it is
    empty exactly when composition failed and the client must render its static
    fallback form for ``fallback``. The stream was validated against the negotiated
    catalog before reaching here (the agent-side phase of A2UI's two-phase
    validation).
    """

    messages: list[dict[str, Any]]
    fallback: str
