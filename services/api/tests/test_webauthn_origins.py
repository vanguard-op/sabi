"""Native passkey origins (FEAT-001).

The native client presents its own platform origin rather than the web origin:
iOS under ``https://<rp_id>`` and Android under
``android:apk-key-hash:<base64url(sha256(cert))>``. The Android origin is
derived from the same signing-certificate fingerprints that back
``/.well-known/assetlinks.json``, so the association file and the WebAuthn
allowlist cannot drift apart (D-038). A valid attestation or assertion must not
be rejected just because the backend only knows the web origin. py_webauthn
matches origins by exact membership, so these tests run the real library
against credentials crafted to carry a native origin.
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

# A real Android signing certificate's SHA-256, uppercase and colon-separated,
# as it appears in assetlinks.json and the deployment configuration.
FINGERPRINT = (
    "51:60:03:F2:CC:9B:70:47:52:A5:EE:4E:DF:A7:0C:5E:"
    "29:F9:77:04:41:CE:5F:B9:6A:23:8B:1D:35:12:5E:99"
)
ANDROID_ORIGIN = "android:apk-key-hash:UWAD8sybcEdSpe5O36cMXin5dwRBzl-5aiOLHTUSXpk"


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
        android_cert_fingerprints=[FINGERPRINT],
    )


def test_allowed_origins_cover_the_web_and_both_native_clients() -> None:
    settings = make_settings(
        webauthn_rp_id="sabi.example",
        webauthn_origin="https://app.sabi.example",
        android_cert_fingerprints=[FINGERPRINT],
    )
    assert settings.webauthn_allowed_origins == [
        "https://app.sabi.example",
        "https://sabi.example",
        ANDROID_ORIGIN,
    ]


def test_android_origin_is_derived_from_the_signing_certificate() -> None:
    assert _native_settings().webauthn_allowed_origins == [
        "http://localhost:8000",
        "https://sabi.example",
        ANDROID_ORIGIN,
    ]


@pytest.mark.parametrize(
    "fingerprint",
    [
        FINGERPRINT,
        FINGERPRINT.lower(),
        FINGERPRINT.replace(":", ""),
        f"  {FINGERPRINT}  ",
    ],
)
def test_fingerprint_format_is_normalised(fingerprint: str) -> None:
    """Colons, case, and surrounding whitespace must not change the origin."""
    settings = make_settings(
        webauthn_rp_id="sabi.example",
        android_cert_fingerprints=[fingerprint],
    )
    assert ANDROID_ORIGIN in settings.webauthn_allowed_origins


def test_blank_fingerprints_are_skipped() -> None:
    settings = make_settings(
        webauthn_rp_id="sabi.example",
        android_cert_fingerprints=["", "   ", FINGERPRINT],
    )
    assert settings.webauthn_allowed_origins == [
        "http://localhost:8000",
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
        android_cert_fingerprints=[FINGERPRINT, FINGERPRINT],
    )
    assert settings.webauthn_allowed_origins == ["https://sabi.example", ANDROID_ORIGIN]


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
