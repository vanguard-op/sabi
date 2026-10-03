"""Wire schemas for the payment authorisation surface (C-017..C-019).

Field names are camelCase on the wire and map to the module's snake_case model
at this boundary (DELIVERY.md, conventions). Amounts are integer minor units
(kobo) paired with a currency; a value is never a float.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["app", "ussd", "sms", "whatsapp"]


class AuthoriseRequest(BaseModel):
    """C-017 request body, exactly as the client sends it.

    ``payee`` is not part of the public body: the authenticated gateway resolves
    the service to its collecting body and forwards it as a trusted value, so
    the module never invents a payee. ``authorisationLimit`` is likewise a trusted
    forwarding of the user's set limit; when absent the configured default applies.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    service_id: str = Field(alias="serviceId", min_length=1, max_length=36)
    amount: int = Field(ge=0)
    currency: Literal["NGN"] = "NGN"
    payee_reference: str | None = Field(default=None, alias="payeeReference", max_length=128)
    payment_method_id: str | None = Field(default=None, alias="paymentMethodId", max_length=36)
    channel: Channel
    second_confirmation: bool = Field(default=False, alias="secondConfirmation")


class AuthoriseResponse(BaseModel):
    """C-017 response body."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(serialization_alias="paymentId")
    status: str
    mandate_id: str = Field(serialization_alias="mandateId")
    rail_reference: str | None = Field(default=None, serialization_alias="railReference")


class ExecuteRequest(BaseModel):
    """C-018 request body.

    ``mandateId`` binds the exact amount and payee; ``Idempotency-Key`` arrives as
    a header, not in the body.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    mandate_id: str = Field(alias="mandateId", min_length=1, max_length=36)


class ExecuteResponse(BaseModel):
    """C-018 response body."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(serialization_alias="paymentId")
    status: str
    rail_reference: str | None = Field(default=None, serialization_alias="railReference")


class PaymentSummary(BaseModel):
    """One item in the C-019 list, snapshotting amount and payee at execution time."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(serialization_alias="paymentId")
    service_id: str = Field(serialization_alias="serviceId")
    amount: int
    currency: str
    payee: str
    status: str
    channel: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class PaymentListResponse(BaseModel):
    """C-019 response body."""

    model_config = ConfigDict(populate_by_name=True)

    payments: list[PaymentSummary]
    next_cursor: str | None = Field(default=None, serialization_alias="nextCursor")


__all__ = [
    "AuthoriseRequest",
    "AuthoriseResponse",
    "Channel",
    "ExecuteRequest",
    "ExecuteResponse",
    "PaymentListResponse",
    "PaymentSummary",
]
