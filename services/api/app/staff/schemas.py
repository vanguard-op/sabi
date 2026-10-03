"""Wire schemas for staff authentication (C-039, C-040).

Field names are camelCase on the wire (DELIVERY.md, conventions). The login
request is validated in the service rather than by FastAPI so an invalid input
returns the contract's 400, not the generic 422 validation envelope.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True)

# Passwords are checked against the stored hash; the shape only bounds absurd
# input so a huge body cannot reach Argon2. The TOTP is six digits.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 256
TOTP_LENGTH = 6


class StaffLoginRequest(BaseModel):
    """C-039 login body."""

    model_config = _CAMEL

    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    totp: str = Field(min_length=TOTP_LENGTH, max_length=TOTP_LENGTH)


class StaffOut(BaseModel):
    """The operator identity returned on a successful login."""

    model_config = _CAMEL

    staff_id: str
    email: str
    role: str


class StaffLoginResponse(BaseModel):
    """C-039 success body; the session itself travels as an HttpOnly cookie."""

    model_config = _CAMEL

    staff: StaffOut
    must_enrol_mfa: bool
