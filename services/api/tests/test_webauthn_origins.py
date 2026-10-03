"""Native passkey origins (FEAT-001).

The native client presents its own platform origin rather than the web origin:
iOS under ``https://<rp_id>`` and Android under ``android:apk-key-hash:<sha256>``.
A valid attestation or assertion must not be rejected just because the backend
only knows the web origin. py_webauthn matches origins by exact membership, so
these tests run the real library against credentials crafted to carry a native
origin.
"""

from __future__ import annotations

import base64
import json

import pytest
from helpers import make_settings
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)

from app.core.config import Settings
from app.identity import passkeys

ANDROID_ORIGIN = "android:apk-key-hash:abc123"


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _client_data(kind: str, challenge: bytes, origin: str) -> str:
    payload = {"type": kind, "challenge": b64(challenge), "origin": origin}
    return b64(json.dumps(payload).encode())


def _registration_credential(challenge: bytes, origin: str) -> dict:
    credential_id = b"native-credential"
    return {
        "id": b64(credential_id),
        "rawId": b64(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": _client_data("webauthn.create", challenge, origin),
            "attestationObject": b64(b"not-a-real-attestation"),
        },
    }


def _assertion_credential(challenge: bytes, origin: str) -> dict:
    credential_id = b"native-credential"
    return {
        "id": b64(credential_id),
        "rawId": b64(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": _client_data("webauthn.get", challenge, origin),
            "authenticatorData": b64(b"not-real-authenticator-data"),
            "signature": b64(b"signature"),
        },
    }


def _native_settings() -> Settings:
    return make_settings(
        webauthn_rp_id="sabi.example",
        webauthn_native_origins=[ANDROID_ORIGIN],
    )


def test_allowed_origins_cover_the_web_and_both_native_clients() -> None:
    settings = make_settings(
        webauthn_rp_id="sabi.example",
        webauthn_origin="https://app.sabi.example",
        webauthn_native_origins=[ANDROID_ORIGIN],
    )
    assert settings.webauthn_allowed_origins == [
        "https://app.sabi.example",
        "https://sabi.example",
        ANDROID_ORIGIN,
    ]


def test_development_default_still_accepts_the_web_origin() -> None:
    settings = make_settings()
    assert "http://localhost:8000" in settings.webauthn_allowed_origins
    assert "https://localhost" in settings.webauthn_allowed_origins


def test_allowed_origins_are_deduplicated() -> None:
    settings = make_settings(
        webauthn_rp_id="sabi.example",
        webauthn_origin="https://sabi.example",
        webauthn_native_origins=["https://sabi.example"],
    )
    assert settings.webauthn_allowed_origins == ["https://sabi.example"]


@pytest.mark.parametrize("origin", [ANDROID_ORIGIN, "https://sabi.example"])
def test_registration_accepts_a_native_origin(origin: str) -> None:
    settings = _native_settings()
    challenge = b"registration-challenge"
    credential = _registration_credential(challenge, origin)

    # The attestation is deliberately unparseable; reaching that later failure
    # proves the native origin cleared the origin check that precedes it.
    with pytest.raises(InvalidRegistrationResponse) as exc:
        passkeys.verify_registration(settings, credential=credential, challenge=challenge)
    assert "origin" not in str(exc.value).lower()


def test_registration_rejects_an_unlisted_origin() -> None:
    settings = _native_settings()
    challenge = b"registration-challenge"
    credential = _registration_credential(challenge, "https://evil.example")

    with pytest.raises(InvalidRegistrationResponse) as exc:
        passkeys.verify_registration(settings, credential=credential, challenge=challenge)
    assert "unexpected client data origin" in str(exc.value).lower()


@pytest.mark.parametrize("origin", [ANDROID_ORIGIN, "https://sabi.example"])
def test_authentication_accepts_a_native_origin(origin: str) -> None:
    settings = _native_settings()
    challenge = b"authentication-challenge"
    credential = _assertion_credential(challenge, origin)

    with pytest.raises(InvalidAuthenticationResponse) as exc:
        passkeys.verify_authentication(
            settings,
            credential=credential,
            challenge=challenge,
            public_key=b"public-key",
            sign_count=0,
        )
    assert "origin" not in str(exc.value).lower()


def test_authentication_rejects_an_unlisted_origin() -> None:
    settings = _native_settings()
    challenge = b"authentication-challenge"
    credential = _assertion_credential(challenge, "https://evil.example")

    with pytest.raises(InvalidAuthenticationResponse) as exc:
        passkeys.verify_authentication(
            settings,
            credential=credential,
            challenge=challenge,
            public_key=b"public-key",
            sign_count=0,
        )
    assert "unexpected client data origin" in str(exc.value).lower()
