"""Wire schemas for the provider registry (C-013 to C-016).

Field names are camelCase on the wire (DELIVERY.md, conventions); the Python
models use snake_case with an alias. Request models validate shape only; the
cross-record rules (duplicate providers, service ownership, amount handling)
live in ``app.registry.service`` so they return the contract's error envelope.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ProviderType(StrEnum):
    AGENCY = "agency"
    BILLER = "biller"
    MERCHANT = "merchant"
    AGGREGATOR = "aggregator"


class AmountSource(StrEnum):
    FIXED = "fixed"
    USER_ENTERED = "user_entered"
    PROVIDER_QUERY = "provider_query"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    QUARANTINE = "quarantine"
    DEREGISTER = "deregister"


class ProviderCreateRequest(BaseModel):
    """C-013 submission."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    type: ProviderType
    contact_email: EmailStr = Field(alias="contactEmail")


class CapabilityCreateRequest(BaseModel):
    """C-014 submission."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    service_id: str | None = Field(default=None, alias="serviceId", max_length=36)
    input_schema_ref: str = Field(alias="inputSchemaRef", min_length=1, max_length=255)
    amount_source: AmountSource = Field(alias="amountSource")
    billable: bool
    price_amount: int | None = Field(default=None, alias="priceAmount", ge=0)
    price_currency: str | None = Field(
        default=None, alias="priceCurrency", min_length=3, max_length=3
    )
    schema_version: str = Field(alias="schemaVersion", min_length=1, max_length=32)


class CapabilityReviewRequest(BaseModel):
    """C-016 review decision."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    decision: ReviewDecision
    reason: str | None = Field(default=None, max_length=2000)
    schema_version: str = Field(alias="schemaVersion", min_length=1, max_length=32)


class ProviderOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    type: str
    contact_email: str | None = Field(default=None, alias="contactEmail")
    status: str
    created_at: str = Field(alias="createdAt")


class CapabilityOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    provider_id: str = Field(alias="providerId")
    service_id: str | None = Field(default=None, alias="serviceId")
    name: str
    input_schema_ref: str = Field(alias="inputSchemaRef")
    amount_source: str = Field(alias="amountSource")
    billable: bool
    price_amount: int | None = Field(default=None, alias="priceAmount")
    price_currency: str | None = Field(default=None, alias="priceCurrency")
    schema_version: str = Field(alias="schemaVersion")
    health_status: str = Field(alias="healthStatus")
    status: str
    created_at: str = Field(alias="createdAt")


class ProviderResponse(BaseModel):
    provider: ProviderOut


class CapabilityResponse(BaseModel):
    capability: CapabilityOut


class CapabilityDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    capability: CapabilityOut
    health_status: str = Field(alias="healthStatus")
