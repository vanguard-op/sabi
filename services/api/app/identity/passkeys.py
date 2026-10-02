"""WebAuthn ceremony wrappers and passkey material encoding.

The private key never reaches the server; only the authenticator's public
credential is held (schema.md, AuthCredential). These wrappers keep the
py_webauthn calls in one place so the service layer stays free of library
detail and the ceremony can be substituted in tests.

The ``AuthCredential.publicKey`` column is a JSON envelope rather than a bare
key: a login assertion identifies a credential by its id, and the frozen schema
has no separate credential-id column, so the id and the COSE public key travel
together. That envelope never leaves the server.
"""

from __future__ import annotations

import json
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    generate_challenge,
    generate_user_handle,
    options_to_json_dict,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import Settings
from app.core.ids import new_id


def new_challenge() -> bytes:
    return generate_challenge()


def new_user_handle() -> bytes:
    """An opaque handle binding the passkey to the future account, not an email."""
    return generate_user_handle()


def new_user_name() -> str:
    """A non-PII user name for the creation options (no phone or email at sign-up)."""
    return new_id()


def registration_options(
    settings: Settings,
    *,
    challenge: bytes,
    user_handle: bytes,
    user_name: str,
) -> dict[str, Any]:
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=user_name,
        user_id=user_handle,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return options_to_json_dict(options)


def authentication_options(settings: Settings, *, challenge: bytes) -> dict[str, Any]:
    # No allow_credentials: sign-in discovers the device's passkey, so the user
    # never types an identifier (FEAT-001).
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        challenge=challenge,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options_to_json_dict(options)


def verify_registration(
    settings: Settings,
    *,
    credential: Any,
    challenge: bytes,
):
    """Verify an attestation or raise ``InvalidRegistrationResponse``."""
    return verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
    )


def verify_authentication(
    settings: Settings,
    *,
    credential: Any,
    challenge: bytes,
    public_key: bytes,
    sign_count: int,
):
    """Verify an assertion or raise ``InvalidAuthenticationResponse``."""
    return verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=settings.webauthn_origin,
        credential_public_key=public_key,
        credential_current_sign_count=sign_count,
    )


def encode_passkey(credential_id: bytes, public_key: bytes) -> str:
    return json.dumps(
        {
            "credentialId": bytes_to_base64url(credential_id),
            "publicKey": bytes_to_base64url(public_key),
        },
        separators=(",", ":"),
    )


def decode_passkey(stored: str) -> tuple[bytes, bytes]:
    data = json.loads(stored)
    return base64url_to_bytes(data["credentialId"]), base64url_to_bytes(data["publicKey"])


def credential_id_of(credential: Any) -> str | None:
    """The normalised base64url credential id from a submitted assertion."""
    raw: Any = None
    if isinstance(credential, dict):
        raw = credential.get("rawId") or credential.get("id")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return bytes_to_base64url(base64url_to_bytes(raw))
    except Exception:
        return None
