"""Composed task surface endpoint (C-012, FEAT-011, MQ-003).

The agent composes a task interface (confirmation, amount entry, receipt, or
discovery) from the client's component catalogue as a declarative UI stream. The
client renders natively; the agent never requests a component outside the
catalogue, and never embeds executable content.

This is a private model-serving surface behind the API gateway: the mobile client
reaches the gateway, which enforces session authentication and rate limiting before
forwarding here. It validates input and returns the frozen C-012 body.

An invalid composition is not an error: the task stays completable through the
client's static fallback form for the same task, so the endpoint answers 200
with ``fallback`` set and an empty ``messages`` list. Only an unknown ``task``
is a 400.
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
# known task is exactly one that has a fallback form.
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

    outcome = serving.compose_surface(task, body.context)
    return SurfaceResponse(messages=list(outcome.messages), fallback=outcome.fallback)
