"""Wire models for receipt retrieval (C-023, C-024, C-025).

Field names are camelCase on the wire (DELIVERY.md, conventions). The full
``Receipt`` mirrors the schema.md entity; ``PaymentSummary`` is the same shape
C-019 returns for a payment. Timestamps render as RFC 3339 UTC.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReceiptSummary(BaseModel):
    """One receipt in the user's history (C-023)."""

    model_config = ConfigDict(populate_by_name=True)

    receipt_id: str = Field(alias="receiptId")
    payment_id: str = Field(alias="paymentId")
    reference: str
    payee: str
    amount: int
    currency: str
    kind: str
    status: str
    issued_at: str | None = Field(default=None, alias="issuedAt")


class ReceiptOut(BaseModel):
    """A full receipt record (C-024), mirroring schema.md ``Receipt``."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    payment_id: str = Field(alias="paymentId")
    user_id: str = Field(alias="userId")
    kind: str
    receipt_number: str | None = Field(default=None, alias="receiptNumber")
    verification_status: str = Field(alias="verificationStatus")
    document_ref: str = Field(alias="documentRef")
    issued_at: str | None = Field(default=None, alias="issuedAt")
    created_at: str = Field(alias="createdAt")


class PaymentSummary(BaseModel):
    """The payment a receipt proves (C-024); the same shape C-019 returns."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(alias="paymentId")
    service_id: str = Field(alias="serviceId")
    amount: int
    currency: str
    payee: str
    status: str
    channel: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class ReceiptListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receipts: list[ReceiptSummary]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class ReceiptDetailResponse(BaseModel):
    receipt: ReceiptOut
    payment: PaymentSummary


class ReceiptDocumentResponse(BaseModel):
    """The stored document behind a receipt (C-025)."""

    model_config = ConfigDict(populate_by_name=True)

    document_ref: str = Field(alias="documentRef")
    content_type: str = Field(alias="contentType")
    share_token: str | None = Field(default=None, alias="shareToken")
