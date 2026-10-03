"""Payment-intent extraction endpoint (FEAT-005, FEAT-009, MQ-001).

Turns a free-form payment request into the grounded amount and payee the client
confirms before authorisation, with candidates to choose from when more than one
service matches (user-flow Flow 2). The model selects a catalogue service and states an
amount traceable to the user's words or the catalogue, and the payee is the grounded
record's collecting body, so an amount or payee is never invented.

This is a private model-serving surface behind the API gateway: the mobile client and
the channels reach the gateway, which enforces session authentication and rate limiting
and forwards here. It validates input and returns the camelCase body that maps onto the
C-017 authorise inputs (``serviceId``, ``amount``, ``currency``, ``payeeReference``) and
the payee and amount the C-026/C-027 case and payment records carry. A request the
model cannot resolve is not an error: it returns an unresolved intent with exactly one
clarifying question, and no payment can start from it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from payment_intent.deps import get_payment_intent_service
from payment_intent.errors import error_response
from payment_intent.schemas import PaymentIntentRequest, PaymentIntentResponse
from payment_intent.service import PaymentIntentService

router = APIRouter(tags=["agent"])

# Bounds and vocabularies shared with the C-009 agent surface: the same client text
# and channel reach this endpoint through the gateway.
_MAX_TEXT_LENGTH = 200
_LOCALES = frozenset({"en", "pcm"})
_CHANNELS = frozenset({"app", "ussd", "sms", "whatsapp"})

_service = Depends(get_payment_intent_service)


@router.post("/agent/payment-intents", response_model=PaymentIntentResponse)
def extract_payment_intent(
    body: PaymentIntentRequest,
    service: PaymentIntentService = _service,
) -> PaymentIntentResponse | JSONResponse:
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

    outcome = service.extract(text, locale=body.locale, channel=body.channel)
    return outcome.response
