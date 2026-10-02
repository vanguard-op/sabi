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

from typing import Annotated

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
_LOCALES = frozenset({"en", "pcm"})
_CHANNELS = frozenset({"app", "ussd", "sms", "whatsapp"})

AccountOwner = Annotated[SessionData, Depends(current_user)]
AgentClient = Annotated[AgentAIClient, Depends(get_agent_client)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


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

    return client.resolve_intent(text=text, locale=payload.locale, channel=payload.channel)


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
