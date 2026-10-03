"""Wire schemas for identity verification (C-020..C-022).

Field names are camelCase on the wire (DELIVERY.md, conventions). The identifier
is submitted once and never echoed back: only its masked form is exposed, and
only through the verification record the contract defines. ``reason`` is a plain,
user-readable sentence, never a raw provider payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.core.time import to_rfc3339

_CAMEL = ConfigDict(alias_generator=lambda name: _to_camel(name), populate_by_name=True)

Method = Literal["nin", "bvn"]
VerificationStatus = Literal["pending", "verified", "failed", "corrected"]
KycStatus = Literal["unverified", "pending", "verified", "rejected"]


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


# RFC 3339 UTC with a trailing Z, independent of whether the driver returned an
# aware or naive value (SQLite in tests stores naive datetimes).
UTCMoment = Annotated[datetime, PlainSerializer(to_rfc3339, return_type=str)]


class VerificationCreateRequest(BaseModel):
    model_config = _CAMEL

    method: Method
    identifier: str


class VerificationCreatedResponse(BaseModel):
    model_config = _CAMEL

    verification_id: str
    status: VerificationStatus


class VerificationDetailResponse(BaseModel):
    model_config = _CAMEL

    verification_id: str
    method: Method
    status: VerificationStatus
    reason: str | None
    verified_at: UTCMoment | None


class AccountVerificationResponse(BaseModel):
    model_config = _CAMEL

    kyc_status: KycStatus
    method: Method | None
    can_correct: bool
