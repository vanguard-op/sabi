"""Gateway agent endpoints (C-009, C-012; FEAT-003, FEAT-011).

The gateway is the client's single entry point (architecture.md, "API Gateway /
Backend-for-Frontend"). These routes enforce the authenticated account-owner
session and the module rate limit, validate the contract bounds, and forward the
call to the AI service, which owns intent resolution and interface composition.
The response body is the AI service's, unchanged: the gateway neither reshapes
nor fabricates it.

Auth and errors are the frozen contract: a missing session is 401; empty or
oversized text, an unsupported locale or channel, and an unknown surface task are
400 with the shared envelope; rate limiting is 429. An AI service that cannot be
reached is 503 with ``ai_unavailable``, since the gateway has no grounded answer
of its own to give.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.agent.client import AgentAIClient
from app.agent.deps import get_agent_client
from app.agent.schemas import (
    IntentRequest,
    IntentResponse,
    SurfaceRequest,
    SurfaceResponse,
)
from app.api.deps import current_user, get_rate_limiter
from app.core.errors import APIError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData

router = APIRouter(tags=["agent"])

# C-009 bounds and vocabularies.
_MAX_TEXT_LENGTH = 200
_MAX_HISTORY_ENTRIES = 6
_LOCALES = frozenset({"en", "pcm"})
_CHANNELS = frozenset({"app", "ussd", "sms", "whatsapp"})
_HISTORY_ROLES = frozenset({"user", "assistant"})
_HISTORY_INVALID = "That conversation history is not valid."

AccountOwner = Annotated[SessionData, Depends(current_user)]
AgentClient = Annotated[AgentAIClient, Depends(get_agent_client)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


def _validated_history(raw: Any) -> list[dict[str, str]] | None:
    """Return the C-009 conversation history, or raise the contract's 400.

    The request declares ``history`` loosely so a malformed value reaches here
    and gets the shared envelope instead of the framework's 422. Each entry must
    be an object whose ``role`` is ``user`` or ``assistant`` and whose ``text``
    is a string; order is preserved and the entries are forwarded as received.
    """

    if raw is None:
        return None
    if not isinstance(raw, list):
        raise APIError(400, ErrorCode.INVALID_REQUEST, _HISTORY_INVALID)
    if len(raw) > _MAX_HISTORY_ENTRIES:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That conversation is too long.")
    history: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise APIError(400, ErrorCode.INVALID_REQUEST, _HISTORY_INVALID)
        role = entry.get("role")
        text = entry.get("text")
        if not isinstance(role, str) or role not in _HISTORY_ROLES or not isinstance(text, str):
            raise APIError(400, ErrorCode.INVALID_REQUEST, _HISTORY_INVALID)
        history.append(entry)
    return history


@router.post("/agent/intents", response_model=IntentResponse)
def resolve_intent(
    payload: IntentRequest,
    session: AccountOwner,
    client: AgentClient,
    limiter: Limiter,
) -> dict:
    # Limit before validation so a burst of malformed requests cannot outrun it.
    limiter.check(f"agent:intents:{session.user_id}")

    text = (payload.text or "").strip()
    if not text:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Enter what you want to pay.")
    if len(text) > _MAX_TEXT_LENGTH:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That request is too long.")
    if payload.locale not in _LOCALES:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That locale is not supported.")
    if payload.channel not in _CHANNELS:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That channel is not supported.")
    history = _validated_history(payload.history)

    return client.resolve_intent(
        text=text, locale=payload.locale, channel=payload.channel, history=history
    )


@router.post("/agent/surfaces", response_model=SurfaceResponse)
def compose_surface(
    payload: SurfaceRequest,
    session: AccountOwner,
    client: AgentClient,
    limiter: Limiter,
) -> dict:
    limiter.check(f"agent:surfaces:{session.user_id}")

    task = (payload.task or "").strip()
    if not task:
        # An unknown (including missing) task is a client error (C-012). The input
        # is never echoed back.
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That task is not supported.")

    return client.compose_surface(task=task, context=payload.context)
