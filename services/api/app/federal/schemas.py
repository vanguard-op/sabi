"""Wire models for federal government payment flows (C-030, C-031, C-032).

Field names are camelCase on the wire (DELIVERY.md, conventions). Request models
validate shape only; the resolution rules (federal collection, switched
collection account, payment state) live in ``app.federal.service`` so they return
the contract's error envelope. Timestamps render as RFC 3339 UTC.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FederalPrepareRequest(BaseModel):
    """C-030 request: resolve a federal obligation before payment."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    service_id: str = Field(alias="serviceId", min_length=1, max_length=36)
    payer_reference: str | None = Field(default=None, alias="payerReference", max_length=128)


class FederalPrepareResponse(BaseModel):
    """C-030 result: what the payer needs before the payment can proceed."""

    model_config = ConfigDict(populate_by_name=True)

    service_id: str = Field(alias="serviceId")
    collecting_body: str = Field(alias="collectingBody")
    amount: int | None
    currency: str
    requires_reference: bool = Field(alias="requiresReference")
    instructions: str | None


class FederalReceiptResponse(BaseModel):
    """C-031 result, covering both branches.

    A 200 carries the stored FTeR fields and no ``status``/``retryAfterSeconds``;
    a 202 carries ``status`` and ``retryAfterSeconds`` and no receipt fields. The
    service sets only the fields its branch owns and the route serialises with
    ``exclude_none`` so each status returns exactly the contract's shape.
    """

    model_config = ConfigDict(populate_by_name=True)

    receipt_id: str | None = Field(default=None, alias="receiptId")
    receipt_number: str | None = Field(default=None, alias="receiptNumber")
    verification_status: str | None = Field(default=None, alias="verificationStatus")
    status: str | None = None
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")


class FederalReconcileRequest(BaseModel):
    """C-032 request: open a reconciliation against the agency record."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=2000)


class FederalReconcileResponse(BaseModel):
    """C-032 result: the newly opened reconciliation case."""

    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(alias="caseId")
    status: str


__all__ = [
    "FederalPrepareRequest",
    "FederalPrepareResponse",
    "FederalReceiptResponse",
    "FederalReconcileRequest",
    "FederalReconcileResponse",
]
