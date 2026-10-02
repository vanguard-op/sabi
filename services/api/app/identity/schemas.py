"""Wire schemas for the identity and account surfaces (C-001..C-008).

Field names are camelCase on the wire (DELIVERY.md, conventions). The envelope
is exactly what the frozen contracts list: extra internal state, such as a
credential public key, is never exposed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator
from pydantic.alias_generators import to_camel

from app.core.time import to_rfc3339

SUPPORTED_LOCALES = frozenset({"en", "pcm"})

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True)
_CAMEL_ORM = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

# RFC 3339 UTC with a trailing Z, independent of whether the driver returned an
# aware or naive value (SQLite in tests stores naive datetimes).
UTCMoment = Annotated[datetime, PlainSerializer(to_rfc3339, return_type=str)]


class RegisterOptionsRequest(BaseModel):
    model_config = _CAMEL

    locale: str


class RegistrationOptionsResponse(BaseModel):
    model_config = _CAMEL

    challenge_id: str
    public_key: dict[str, Any]


class RegisterVerifyRequest(BaseModel):
    model_config = _CAMEL

    challenge_id: str
    credential: dict[str, Any]
    display_name: str | None = None
    locale: str


class UserOut(BaseModel):
    model_config = _CAMEL_ORM

    id: str
    display_name: str | None
    locale: str
    preferred_channel: str
    kyc_status: str
    account_status: str
    created_at: UTCMoment
    updated_at: UTCMoment


class RegisterVerifyResponse(BaseModel):
    model_config = _CAMEL

    user: UserOut
    recovery_code: str


class LoginOptionsResponse(BaseModel):
    model_config = _CAMEL

    challenge_id: str
    public_key: dict[str, Any]


class LoginVerifyRequest(BaseModel):
    model_config = _CAMEL

    challenge_id: str
    credential: dict[str, Any]


class LoginVerifyResponse(BaseModel):
    model_config = _CAMEL

    user: UserOut


class RecoveryVerifyRequest(BaseModel):
    model_config = _CAMEL

    recovery_code: str


class RecoveryVerifyResponse(BaseModel):
    model_config = _CAMEL

    user: UserOut
    must_enrol_passkey: bool = True


class RecoveryRegenerateResponse(BaseModel):
    model_config = _CAMEL

    recovery_code: str


class ChannelLinkCreateRequest(BaseModel):
    model_config = _CAMEL

    channel: Literal["ussd", "sms", "whatsapp"]
    address: str

    @field_validator("address")
    @classmethod
    def _validate_address(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if normalized is None:
            raise ValueError("address must be a telephone number")
        return normalized


class ChannelLinkOut(BaseModel):
    model_config = _CAMEL_ORM

    id: str
    channel: str
    address: str
    verified_at: UTCMoment | None


class ChannelLinkAccountOut(ChannelLinkOut):
    """The full ChannelLink entity as it appears on the account (C-008)."""

    user_id: str
    created_at: UTCMoment


class AccountMeResponse(BaseModel):
    model_config = _CAMEL_ORM

    id: str
    display_name: str | None
    locale: str
    preferred_channel: str
    kyc_status: str
    account_status: str
    channel_links: list[ChannelLinkAccountOut] = Field(default_factory=list)
    created_at: UTCMoment
    updated_at: UTCMoment


def normalize_phone(raw: str) -> str | None:
    """Normalise a channel address to a comparable telephone number.

    Accepts an optional leading ``+`` and 7–15 digits, ignoring spaces, dashes,
    and parentheses so a number typed differently still maps to one link. Returns
    None when the value is not a plausible telephone number.
    """
    if not isinstance(raw, str):
        return None
    compact = "".join(char for char in raw.strip() if char not in " -().")
    if not compact:
        return None
    digits = compact[1:] if compact.startswith("+") else compact
    plus = "+" if compact.startswith("+") else ""
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        return None
    return f"{plus}{digits}"
