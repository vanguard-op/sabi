"""Wire models for the USSD/SMS channel gateway (C-036 to C-038).

Field names are camelCase on the wire (DELIVERY.md, conventions). The request
models validate shape only; session state, timeout, and authorisation rules live
in ``app.channels.service`` so the agent can return the contract's error
envelope. Responses carry only the contract fields; a prompt is plain text the
USSD gateway renders, and never embeds a secret.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The channel the gateway speaks: USSD for the session, SMS for delivery. The
# account link itself is created and owned by the identity module (C-007).
USSD_CHANNEL = "ussd"

# Session steps, in order. A step names the prompt just shown and the input the
# next call is expected to carry; ``menu`` opens a fresh or resumed session.
STEP_MENU = "menu"
STEP_SERVICE = "service"
STEP_DETAILS = "details"
STEP_CONFIRM = "confirm"
STEP_RESULT = "result"

# Short, localised prompts keep a session inside its airtime budget (NFR-006).
# ``pcm`` falls back to English with a note where a translation is not held.
PROMPTS: dict[str, dict[str, str]] = {
    "menu": {
        "en": "Sabi. 1 Pay a bill. 2 Check a payment. Reply with a number.",
        "pcm": "Sabi. 1 Pay bill. 2 Check payment. Reply with number.",
    },
    "service": {
        "en": "Which service? Reply with the number shown.",
        "pcm": "Which service? Reply with the number.",
    },
    "details": {
        "en": "Enter the meter or phone number.",
        "pcm": "Enter meter or phone number.",
    },
    "confirm": {
        "en": "Confirm the amount and the charge for this session. 1 Yes. 2 No.",
        "pcm": "Confirm amount and session charge. 1 Yes. 2 No.",
    },
    "result": {
        "en": "Done. Your reference will arrive by SMS.",
        "pcm": "Done. Reference go come by SMS.",
    },
    "timed_out": {
        "en": "Session timed out. Dial again to continue.",
        "pcm": "Session don finish. Dial again to continue.",
    },
    "timed_out_pending": {
        "en": "Session timed out. Your payment is pending; dial again to continue.",
        "pcm": "Session don finish. Payment still pending; dial again to continue.",
    },
    "unlinked": {
        "en": "That number is not linked to a Sabi account. Link it in the app first.",
        "pcm": "That number no dey linked to Sabi. Link am for app first.",
    },
    "invalid": {
        "en": "That reply was not understood. Try again.",
        "pcm": "We no understand that reply. Try again.",
    },
}

# Affirmative replies accepted at the confirmation step. The confirmation is one
# short input on a keypad, so ``1`` and ``yes`` are the common forms.
AFFIRMATIVE = frozenset({"1", "y", "yes"})


class UssdSessionRequest(BaseModel):
    """C-036 request. ``input`` and ``step`` are null on the opening call."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    session_id: str = Field(alias="sessionId", min_length=1, max_length=128)
    msisdn: str = Field(min_length=1, max_length=32)
    input: str | None = Field(default=None, max_length=64)
    step: str | None = Field(default=None, max_length=32)

    @field_validator("msisdn")
    @classmethod
    def _normalise_msisdn(cls, value: str) -> str:
        # A channel address is a telephone number; keep a leading + and digits
        # only, so the same subscriber always resolves to one normalised form.
        digits = value.strip()
        prefix = "+" if digits.startswith("+") else ""
        digits = "".join(ch for ch in digits if ch.isdigit())
        if not digits:
            raise ValueError("msisdn must be a telephone number")
        return prefix + digits


class UssdSessionResponse(BaseModel):
    """C-036 response: the next prompt and the step it belongs to."""

    model_config = ConfigDict(populate_by_name=True)

    prompt: str
    step: str
    done: bool


class UssdAuthoriseRequest(BaseModel):
    """C-037 request. The idempotency key arrives as a header."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    session_id: str = Field(alias="sessionId", min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=64)


class UssdAuthoriseResponse(BaseModel):
    """C-037 response: the payment outcome and its rail reference."""

    model_config = ConfigDict(populate_by_name=True)

    status: str
    reference: str | None = None


class SmsStatusResponse(BaseModel):
    """C-038 response: delivery status of an SMS and any token it carried."""

    model_config = ConfigDict(populate_by_name=True)

    reference: str
    status: str
    token: str | None = None


__all__ = [
    "AFFIRMATIVE",
    "PROMPTS",
    "STEP_CONFIRM",
    "STEP_DETAILS",
    "STEP_MENU",
    "STEP_RESULT",
    "STEP_SERVICE",
    "USSD_CHANNEL",
    "SmsStatusResponse",
    "UssdAuthoriseRequest",
    "UssdAuthoriseResponse",
    "UssdSessionRequest",
    "UssdSessionResponse",
]
