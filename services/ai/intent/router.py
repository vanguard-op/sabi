"""C-009: POST /v1/agent/intents.

Turns a free-form request into a structured intent (intent resolution, FEAT-003,
MQ-001) and returns it with the candidate service records the client renders. This
module is the HTTP adapter only: the model call, grounding, guardrails, and fallback
live in :mod:`core.serving`.

This is a private model-serving surface behind the API gateway: the mobile client
reaches the gateway, which enforces session authentication and rate limiting before
forwarding here. It validates input and returns the frozen C-009 body.

Contract conformance (CONTRACTS.md, C-009):
- ``text`` is required, non-empty, and at most 200 characters; ``locale`` is ``en`` or
  ``pcm``; ``channel`` is ``app``, ``ussd``, ``sms``, or ``whatsapp``. A missing or
  malformed field is 400 (the app maps schema failures to that envelope), rate
  limiting is a gateway concern.
- ``history`` is optional, oldest first, at most six turns of
  ``{role: user|assistant, text}``; a malformed entry, an unknown role, or an oversized
  list is 400. The earlier turns are rendered into the prompt so each clarification
  builds on the answers already given, and the three-question bound is counted from
  them. A greeting or other non-command message resolves to ``non_command``: no
  clarifying question, no payment field, and nothing recorded for coverage.
- ``candidates`` is the optional grounding set the gateway forwards on this private
  hop: the candidate services it already holds, in the ``ServiceSummary`` shape. When
  present it is the authoritative retrieval set for grounding and replaces the
  service's own index, so the model can set ``target`` to a real service id (D-043);
  when absent the local index is used as before. It is not part of the client-facing
  C-009 request, and an over-sized set is 400.
- The 200 body is camelCase: ``intent`` (``intentType``, ``target``, ``amount``,
  ``currency``, ``reference``, ``constraints``, ``confidence``, ``language``,
  ``clarifyingQuestion``), ``candidates`` (``serviceId``, ``name``,
  ``collectingBody``, ``category``, ``knownAmount``, ``currency``, ``status``,
  ``confidence``), and ``source`` (``model`` or ``fallback``). The model-internal
  snake_case schema never crosses this boundary (D-018).
- ``source`` is ``fallback`` whenever the pinned provider is unavailable, times out,
  or returns output outside the contract; that path degrades to keyword and search
  resolution and always carries an unresolved intent that requires confirmation, so a
  payment can never start from a degraded answer (MQ-001 Fallback).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from core.history import ConversationTurn
from intent.deps import get_intent_service
from intent.errors import error_response
from intent.schemas import (
    MAX_CANDIDATES,
    IntentRequest,
    IntentResponse,
    candidates_to_records,
)
from intent.service import IntentService

router = APIRouter(tags=["agent"])

# C-009 bounds and vocabularies.
_MAX_TEXT_LENGTH = 200
_LOCALES = frozenset({"en", "pcm"})
_CHANNELS = frozenset({"app", "ussd", "sms", "whatsapp"})

_serving = Depends(get_intent_service)


@router.post("/agent/intents", response_model=IntentResponse)
def resolve_intent(
    body: IntentRequest,
    service: IntentService = _serving,
) -> IntentResponse | JSONResponse:
    text = body.text.strip()
    if not text:
        # The contract treats empty text as invalid input, not a schema failure.
        return error_response(400, "invalid_request", "Enter what you want to pay.")
    if len(text) > _MAX_TEXT_LENGTH:
        return error_response(400, "invalid_request", "That request is too long.")
    if body.locale not in _LOCALES:
        return error_response(400, "invalid_request", "That locale is not supported.")
    if body.channel not in _CHANNELS:
        return error_response(400, "invalid_request", "That channel is not supported.")

    raw_candidates = body.candidates or []
    if len(raw_candidates) > MAX_CANDIDATES:
        return error_response(400, "invalid_request", "That candidate set is too large.")

    history = tuple(
        ConversationTurn(role=turn.role, text=turn.text) for turn in (body.history or [])
    )
    outcome = service.resolve(
        text,
        locale=body.locale,
        channel=body.channel,
        history=history,
        candidates=candidates_to_records(raw_candidates),
    )
    return outcome.response
