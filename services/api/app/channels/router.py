"""USSD and SMS channel HTTP surface (C-036 to C-038).

Paths are declared without the ``/v1`` prefix; the app factory mounts the router
under it (DELIVERY.md, conventions). These endpoints authenticate the channel
identity, not an app session: the USSD/SMS aggregator supplies the subscriber's
MSISDN, and no end-user cookie is involved. On C-036 and C-037 the MSISDN is part
of the session (``msisdn`` on the open call; the bound session thereafter). C-038
has no request body, so the subscriber arrives in the ``X-Channel-Msisdn`` header,
which is the channel-identity credential and is never logged or echoed.

A missing MSISDN on C-038 is reported as an unknown reference rather than a
distinct error: the contract's only failure for that surface is 404, and
ownership of another number's message must not be inferable from the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_settings
from app.channels import service
from app.channels.ports import (
    ChannelIdentityLookup,
    ChannelPaymentPort,
    SmsDeliveryPort,
    get_channel_identity,
    get_channel_payments,
    get_sms_delivery,
    get_ussd_session_store,
)
from app.channels.schemas import (
    SmsStatusResponse,
    UssdAuthoriseRequest,
    UssdAuthoriseResponse,
    UssdSessionRequest,
    UssdSessionResponse,
)
from app.channels.sessions import UssdSessionStore
from app.core.config import Settings

router = APIRouter(tags=["channels"])

IdentityLookup = Annotated[ChannelIdentityLookup, Depends(get_channel_identity)]
PaymentBoundary = Annotated[ChannelPaymentPort, Depends(get_channel_payments)]
SmsBoundary = Annotated[SmsDeliveryPort, Depends(get_sms_delivery)]
SessionStore = Annotated[UssdSessionStore, Depends(get_ussd_session_store)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("/channels/ussd/session", response_model=UssdSessionResponse)
def ussd_session(
    request: UssdSessionRequest,
    identity: IdentityLookup,
    payments: PaymentBoundary,
    store: SessionStore,
    settings: AppSettings,
) -> UssdSessionResponse:
    result = service.open_or_advance(
        store=store,
        identity=identity,
        payments=payments,
        session_id=request.session_id,
        msisdn=request.msisdn,
        input_value=request.input,
        step=request.step,
        timeout_seconds=settings.channel_session_timeout_seconds,
    )
    return UssdSessionResponse.model_validate(result)


@router.post("/channels/ussd/authorise", response_model=UssdAuthoriseResponse)
def ussd_authorise(
    request: UssdAuthoriseRequest,
    payments: PaymentBoundary,
    sms: SmsBoundary,
    store: SessionStore,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> UssdAuthoriseResponse:
    result = service.authorise(
        store=store,
        payments=payments,
        session_id=request.session_id,
        confirmation=request.confirmation,
        idempotency_key=idempotency_key,
    )
    # Deliver the reference by SMS; a delivery failure is retained for retry at
    # the notification service and does not fail the payment.
    reference = result.get("reference")
    session = store.get(request.session_id)
    if isinstance(reference, str) and reference and session is not None:
        service.deliver_reference(sms=sms, msisdn=session.msisdn, reference=reference)
    return UssdAuthoriseResponse.model_validate(result)


@router.get("/channels/sms/status/{reference}", response_model=SmsStatusResponse)
def sms_status(
    reference: str,
    sms: SmsBoundary,
    msisdn: str | None = Header(default=None, alias="X-Channel-Msisdn"),
) -> SmsStatusResponse:
    # A channel identity that is absent cannot prove ownership of any message, so
    # it resolves as unknown rather than revealing that the reference exists.
    result = service.sms_status(sms=sms, msisdn=msisdn or "", reference=reference)
    return SmsStatusResponse.model_validate(result)
