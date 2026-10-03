"""Wire models for everyday bill payment flows (C-033, C-034, C-035).

Field names are camelCase on the wire (DELIVERY.md, conventions). Request models
validate shape only; the resolution rules (known biller, offline biller, token
state) live in ``app.bills.service`` so they return the contract's error
envelope. Amounts are integer minor units (kobo) paired with a currency.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BillValidateRequest(BaseModel):
    """C-033 request: check a recipient, and optionally an amount, before paying."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    service_id: str = Field(alias="serviceId", min_length=1, max_length=36)
    recipient_identifier: str = Field(alias="recipientIdentifier", max_length=128)
    amount: int | None = None


class BillRangeOut(BaseModel):
    """The accepted amount band for a variable bill, in minor units."""

    minimum: int
    maximum: int


class BillValidateResponse(BaseModel):
    """C-033 result: whether the recipient can be paid and the amount rules."""

    model_config = ConfigDict(populate_by_name=True)

    valid: bool
    recipient_identifier: str = Field(alias="recipientIdentifier")
    known_amount: int | None = Field(default=None, alias="knownAmount")
    currency: str
    range: BillRangeOut | None = None
    reason: str | None = None


class BillPaymentRequest(BaseModel):
    """C-034 request: pay a bill in one authorise-and-execute step."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    service_id: str = Field(alias="serviceId", min_length=1, max_length=36)
    recipient_identifier: str = Field(alias="recipientIdentifier", max_length=128)
    amount: int
    currency: str = Field(default="NGN", min_length=3, max_length=3)


class BillPaymentResponse(BaseModel):
    """C-034 result: the payment, and the token or receipt it produced."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(alias="paymentId")
    status: str
    token: str | None = None
    receipt_id: str | None = Field(default=None, alias="receiptId")


class BillTokenResponse(BaseModel):
    """C-035 result, covering both branches.

    A 200 carries the token and its receipt id and no ``status``; a 202 carries
    ``status`` and ``retryAfterSeconds``. The service sets only the fields its
    branch owns and the route serialises with ``exclude_none`` so each status
    returns exactly the contract's shape.
    """

    model_config = ConfigDict(populate_by_name=True)

    token: str | None = None
    receipt_id: str | None = Field(default=None, alias="receiptId")
    status: str | None = None
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")


__all__ = [
    "BillPaymentRequest",
    "BillPaymentResponse",
    "BillRangeOut",
    "BillTokenResponse",
    "BillValidateRequest",
    "BillValidateResponse",
]
