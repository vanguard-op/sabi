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

from intent.deps import get_intent_service
from intent.errors import error_response
from intent.schemas import IntentRequest, IntentResponse
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

    outcome = service.resolve(text, locale=body.locale, channel=body.channel)
    return outcome.response
