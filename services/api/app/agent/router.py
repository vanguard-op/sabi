"""Gateway agent endpoints (C-009, C-012; FEAT-003, FEAT-011).

The gateway is the client's single entry point (architecture.md, "API Gateway /
Backend-for-Frontend"). These routes enforce the authenticated account-owner
session and the module rate limit, validate the contract bounds, and forward the
call to the AI service, which owns intent resolution and interface composition.
The response body is the AI service's, unchanged: the gateway neither reshapes
nor fabricates it.

Auth and errors are the frozen contract: a missing session is 401; empty or
oversized text, an unsupported locale or channel, an unknown surface task, and a
malformed or oversized history are 400 with the shared envelope; rate limiting is
429. An AI service that cannot be reached is 503 with ``ai_unavailable``, since
the gateway has no grounded answer of its own to give.

The gateway owns the primary catalogue, so it grounds the intent call: before
forwarding, it ranks the catalogue for the request text and sends a bounded set
of candidate services as an internal ``candidates`` array. That set is not part
of the frozen C-009 request or response; the AI service grounds on it rather
than its own retrieval index (D-043).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.client import AgentAIClient
from app.agent.deps import get_agent_client
from app.agent.schemas import (
    IntentRequest,
    IntentResponse,
    SurfaceRequest,
    SurfaceResponse,
)
from app.api.deps import current_user, get_rate_limiter
from app.catalogue import repository
from app.catalogue.search import rank
from app.core.errors import APIError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData
from app.db.session import get_db

router = APIRouter(tags=["agent"])

# C-009 bounds and vocabularies.
_MAX_TEXT_LENGTH = 200
_MAX_HISTORY_ENTRIES = 6
_LOCALES = frozenset({"en", "pcm"})
_CHANNELS = frozenset({"app", "ussd", "sms", "whatsapp"})
_HISTORY_ROLES = frozenset({"user", "assistant"})
_HISTORY_INVALID = "That conversation history is not valid."

# C-012 task vocabulary. Every task has a client fallback form, so the gateway
# accepts exactly the composed task types the contract names; anything else is the
# contract's unknown-task 400. ``receipt`` covers both a post-payment receipt and a
# resolved record the user asked about: the task is the same, and the resolved
# record reference rides in ``context``, which is forwarded unchanged.
_SURFACE_TASKS = frozenset(
    {"confirmation", "amount_entry", "receipt", "discovery", "verification", "recovery"}
)

# Grounding candidates forwarded to the AI service are bounded so a request can
# never grow the prompt without limit. The cap matches the AI service's own
# retrieval breadth.
_MAX_CANDIDATES = 20

AccountOwner = Annotated[SessionData, Depends(current_user)]
AgentClient = Annotated[AgentAIClient, Depends(get_agent_client)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
DbSession = Annotated[Session, Depends(get_db)]


def _forwarded_candidates(db: Session, query: str) -> list[dict[str, Any]]:
    """Rank the gateway catalogue for ``query`` and serialise the top matches.

    The records are the C-009 ``ServiceSummary`` fields the AI service grounds on
    (camelCase, D-018). An empty catalogue or no match yields no candidates, so
    nothing is forwarded and the AI service falls back to its own index. Retrieved
    content is untrusted, so this is only a relevance-ranked set, never an
    instruction.
    """

    matches = rank(repository.candidates(db), query, _MAX_CANDIDATES)
    return [
        {
            "serviceId": service.id,
            "name": service.name,
            "collectingBody": service.collecting_body,
            "category": service.category,
            "knownAmount": service.known_amount,
            "currency": service.currency,
            "status": service.status,
        }
        for service, _confidence in matches
    ]


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
    db: DbSession,
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

    # Ground the AI call in the gateway's own catalogue; the AI's retrieval index
    # is not installed, so an ungrounded call cannot resolve a real service.
    candidates = _forwarded_candidates(db, text)

    return client.resolve_intent(
        text=text,
        locale=payload.locale,
        channel=payload.channel,
        history=history,
        candidates=candidates,
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
    if task not in _SURFACE_TASKS:
        # An unknown (including missing) task is a client error (C-012). The input
        # is never echoed back.
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That task is not supported.")

    # The context is untrusted, free-form task data; a resolved record reference for
    # a ``receipt`` task is carried here and forwarded exactly as received. The
    # gateway neither composes nor reshapes: the AI service owns composition.
    #
    # ``catalogId`` is the client's published Sabi A2UI catalog, negotiated from
    # its supportedCatalogIds (C-012 revision 2). The gateway validates and
    # forwards it unchanged; whether the named catalog is one the agent can speak,
    # and the A2UI validation of the composed stream, are the AI service's job.
    return client.compose_surface(
        task=task,
        context=payload.context,
        catalog_id=payload.catalog_id,
    )
