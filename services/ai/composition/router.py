"""Composed task surface endpoint (C-012, FEAT-011, MQ-003).

The agent composes a task interface against the client's published Sabi A2UI catalog
and returns an A2UI v0.9 message stream: service payment (confirmation, amount entry),
discovery, identity verification, failed-payment or case recovery, and the composed
rendering of a resolved record the user asked about (a receipt task whose context
carries a resolved record reference from a record lookup, not only a post-payment
service payment). The client renders natively through the official GenUI SDK; the
agent never requests a component outside the catalog, and never embeds executable
content.

The catalog is negotiated from the ``catalogId`` on the request (A2UI catalog
negotiation), and the composed stream is validated against it before sending (the
agent-side phase of A2UI's two-phase validation), so a hallucinated component is
caught before the payload is sent.

This is a private model-serving surface behind the API gateway: the mobile client
reaches the gateway, which enforces session authentication and rate limiting before
forwarding here. It validates input and returns the frozen C-012 body.

An invalid composition is not an error: the task stays completable through the
client's static fallback form for the same task, so the endpoint answers 200
with ``fallback`` set and an empty ``messages`` list. The same holds when no
compatible catalog is negotiated: the spec requires a fallback, not a failure. Only
an unknown ``task`` is a 400.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from composition.dependencies import get_serving
from composition.errors import error_response
from composition.schemas import SurfaceRequest, SurfaceResponse
from core.schemas import FALLBACK_TASKS
from core.serving import ModelServing

router = APIRouter(tags=["composition"])

# Every task has a client fallback (screens.md, "Composed Task Surface"), so a
# known task is exactly one that has a fallback form: confirmation, amount_entry,
# receipt, discovery, verification, recovery (C-012, FEAT-011).
_KNOWN_TASKS = FALLBACK_TASKS

_serving = Depends(get_serving)


@router.post("/agent/surfaces", response_model=SurfaceResponse)
def compose_surface(
    body: SurfaceRequest,
    serving: ModelServing = _serving,
) -> SurfaceResponse | JSONResponse:
    task = body.task.strip()
    if task not in _KNOWN_TASKS:
        # Unknown task is a client error (C-012). Known-but-uncomposable tasks
        # fall through to the fallback below. The input is never echoed back.
        return error_response(400, "invalid_request", "That task is not supported.")

    # The catalog id is the client's published Sabi A2UI catalog, negotiated from
    # its supportedCatalogIds. It is passed to composition unchanged; when it is
    # absent or names no catalog the agent can speak, composition returns the
    # same-task fallback rather than an error (C-012 revision 2).
    outcome = serving.compose_surface(task, body.context, catalog_id=body.catalog_id)
    return SurfaceResponse(messages=list(outcome.messages), fallback=outcome.fallback)
