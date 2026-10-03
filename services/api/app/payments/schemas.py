"""Wire models for the gateway payment endpoints (C-017..C-019).

The gateway forwards the payment module's JSON body unchanged, so these models
are the contract boundary: they validate the inbound request and give the
OpenAPI document the frozen response shape. Field names are camelCase on the
wire (DELIVERY.md, conventions); the module speaks the same shape, so no
reshaping happens here.

Request fields that the gateway resolves from trusted state (the collecting
body, the user's authorisation limit, the service type) are absent from these
models: they are never read from the client body.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

Channel = str

# The two collections the payment module distinguishes for its own policy; the
# vocabulary matches the catalogue's ``Service.type``.
_SERVICE_TYPES = frozenset({"government", "biller", "merchant"})


class AuthoriseRequest(BaseModel):
    """The C-017 request body, exactly as the client sends it.

    ``secondConfirmation`` is optional at the schema layer so the router can
    return the contract's error for a missing confirmation rather than the
    framework's 422. An empty ``paymentMethodId`` is treated as absent.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    service_id: str | None = Field(default=None, alias="serviceId", max_length=36)
    amount: int
    currency: str = "NGN"
    payee_reference: str | None = Field(default=None, alias="payeeReference", max_length=128)
    payment_method_id: str | None = Field(default=None, alias="paymentMethodId", max_length=36)
    channel: str = "app"
    second_confirmation: bool = Field(default=False, alias="secondConfirmation")


class ExecuteRequest(BaseModel):
    """The C-018 request body. ``mandateId`` binds the exact amount and payee."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    mandate_id: str | None = Field(default=None, alias="mandateId", max_length=36)


class AuthoriseResponse(BaseModel):
    """The C-017 response body, as the payment module returns it."""

    model_config = ConfigDict(populate_by_name=True)

    paymentId: str
    status: str
    mandateId: str
    railReference: str | None = None


class ExecuteResponse(BaseModel):
    """The C-018 response body, as the payment module returns it."""

    model_config = ConfigDict(populate_by_name=True)

    paymentId: str
    status: str
    railReference: str | None = None


class PaymentSummaryOut(BaseModel):
    """One item in the C-019 list, snapshotted at execution time."""

    model_config = ConfigDict(populate_by_name=True)

    paymentId: str
    serviceId: str
    amount: int
    currency: str
    payee: str
    status: str
    channel: str
    createdAt: str
    updatedAt: str


class PaymentListResponse(BaseModel):
    """The C-019 response body."""

    model_config = ConfigDict(populate_by_name=True)

    payments: list[PaymentSummaryOut]
    nextCursor: str | None = None


__all__ = [
    "AuthoriseRequest",
    "AuthoriseResponse",
    "Channel",
    "ExecuteRequest",
    "ExecuteResponse",
    "PaymentListResponse",
    "PaymentSummaryOut",
]
