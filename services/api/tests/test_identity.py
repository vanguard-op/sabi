"""Identity flows (C-001..C-008): registration, sign-in, recovery, links, account.

The WebAuthn ceremony itself is the library's tested responsibility; these tests
substitute the verify calls and assert the service's contract behaviour: status
codes, error codes, single-use semantics, link ownership, and what reaches the
wire.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)

from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.db.models import ChannelLink, Notification
from app.identity import passkeys
from app.identity.challenges import Challenge, ChallengeKind, InMemoryChallengeStore
from app.identity.schemas import normalize_phone


@pytest.fixture
def identity(
    app: FastAPI, client: TestClient, db_session_factory: sessionmaker[Session]
) -> TestClient:
    """The shared client, wired to an isolated SQLite store and a permissive limiter."""
    app.state.session_factory = db_session_factory
    app.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=100, default_window_seconds=60
    )
    return client


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _register(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    credential_id: bytes = b"credential-one",
    public_key: bytes = b"public-key-one",
    sign_count: int = 0,
    locale: str = "en",
    display_name: str | None = "Ngozi",
):
    options = client.post("/v1/auth/register/options", json={"locale": locale})
    challenge_id = options.json()["challengeId"]
    verified = SimpleNamespace(
        credential_id=credential_id,
        credential_public_key=public_key,
        sign_count=sign_count,
    )
    monkeypatch.setattr(passkeys, "verify_registration", lambda *a, **k: verified)
    return client.post(
        "/v1/auth/register/verify",
        json={
            "challengeId": challenge_id,
            "credential": {"id": b64(credential_id)},
            "displayName": display_name,
            "locale": locale,
        },
    )


def _login_options(client: TestClient) -> str:
    response = client.post("/v1/auth/login/options")
    assert response.status_code == 200, response.text
    return response.json()["challengeId"]


def _login_accept(monkeypatch: pytest.MonkeyPatch, *, new_sign_count: int = 1) -> None:
    verified = SimpleNamespace(new_sign_count=new_sign_count)
    monkeypatch.setattr(passkeys, "verify_authentication", lambda *a, **k: verified)


def test_register_creates_account_and_returns_recovery_code_once(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _register(identity, monkeypatch)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recoveryCode"]
    assert body["user"]["displayName"] == "Ngozi"
    assert body["user"]["locale"] == "en"
    assert body["user"]["preferredChannel"] == "app"
    assert body["user"]["kycStatus"] == "unverified"
    assert body["user"]["accountStatus"] == "active"
    assert body["user"]["createdAt"].endswith("Z")
    assert "sabi_session" in response.cookies

    me = identity.get("/v1/account/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]
    assert me.json()["channelLinks"] == []


def test_register_options_rejects_unsupported_locale(identity: TestClient) -> None:
    response = identity.post("/v1/auth/register/options", json={"locale": "fr"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_register_verify_rejects_unknown_challenge(identity: TestClient) -> None:
    response = identity.post(
        "/v1/auth/register/verify",
        json={
            "challengeId": "not-a-challenge",
            "credential": {},
            "displayName": None,
            "locale": "en",
        },
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "challenge_expired"


def test_register_verify_invalid_attestation_consumes_challenge(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = identity.post("/v1/auth/register/options", json={"locale": "en"})
    challenge_id = options.json()["challengeId"]

    def _reject(*a, **k):
        raise InvalidRegistrationResponse("bad attestation")

    monkeypatch.setattr(passkeys, "verify_registration", _reject)
    payload = {
        "challengeId": challenge_id,
        "credential": {},
        "displayName": None,
        "locale": "en",
    }
    first = identity.post("/v1/auth/register/verify", json=payload)
    assert first.status_code == 400
    assert first.json()["error"]["code"] == "invalid_request"

    # The challenge was consumed, so a retry cannot reuse it.
    second = identity.post("/v1/auth/register/verify", json=payload)
    assert second.status_code == 410


def test_duplicate_passkey_is_rejected(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _register(identity, monkeypatch).status_code == 201
    duplicate = _register(identity, monkeypatch)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


def test_login_with_registered_passkey(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered = _register(identity, monkeypatch).json()["user"]
    identity.cookies.clear()

    challenge_id = _login_options(identity)
    _login_accept(monkeypatch)
    response = identity.post(
        "/v1/auth/login/verify",
        json={"challengeId": challenge_id, "credential": {"id": b64(b"credential-one")}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == registered["id"]
    assert identity.get("/v1/account/me").status_code == 200


def test_login_unknown_passkey_is_unauthorized(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge_id = _login_options(identity)
    _login_accept(monkeypatch)
    response = identity.post(
        "/v1/auth/login/verify",
        json={"challengeId": challenge_id, "credential": {"id": b64(b"nobody")}},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_login_invalid_assertion(identity: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _register(identity, monkeypatch)
    identity.cookies.clear()
    challenge_id = _login_options(identity)

    def _reject(*a, **k):
        raise InvalidAuthenticationResponse("bad assertion")

    monkeypatch.setattr(passkeys, "verify_authentication", _reject)
    response = identity.post(
        "/v1/auth/login/verify",
        json={"challengeId": challenge_id, "credential": {"id": b64(b"credential-one")}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_login_verify_rejects_unknown_challenge(identity: TestClient) -> None:
    response = identity.post(
        "/v1/auth/login/verify",
        json={"challengeId": "gone", "credential": {"id": b64(b"x")}},
    )
    assert response.status_code == 410


def test_recovery_code_is_single_use_and_prompts_new_passkey(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recovery_code = _register(identity, monkeypatch).json()["recoveryCode"]
    identity.cookies.clear()

    first = identity.post("/v1/auth/recovery/verify", json={"recoveryCode": recovery_code})
    assert first.status_code == 200, first.text
    assert first.json()["mustEnrolPasskey"] is True
    assert identity.get("/v1/account/me").status_code == 200

    identity.cookies.clear()
    second = identity.post("/v1/auth/recovery/verify", json={"recoveryCode": recovery_code})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_recovery_code_invalid_is_unauthorized(identity: TestClient) -> None:
    response = identity.post("/v1/auth/recovery/verify", json={"recoveryCode": "WRONG-CODE"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_recovery_regenerate_requires_session_and_replaces_the_code(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert identity.post("/v1/auth/recovery/regenerate").status_code == 401

    old_code = _register(identity, monkeypatch).json()["recoveryCode"]
    response = identity.post("/v1/auth/recovery/regenerate")
    assert response.status_code == 200, response.text
    new_code = response.json()["recoveryCode"]
    assert new_code != old_code

    identity.cookies.clear()
    old_attempt = identity.post("/v1/auth/recovery/verify", json={"recoveryCode": old_code})
    assert old_attempt.status_code == 401
    new_attempt = identity.post("/v1/auth/recovery/verify", json={"recoveryCode": new_code})
    assert new_attempt.status_code == 200


def test_channel_link_is_attached_to_the_same_account(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(identity, monkeypatch)
    response = identity.post(
        "/v1/auth/channel-links",
        json={"channel": "whatsapp", "address": "+234 803 123 4567"},
    )
    assert response.status_code == 201, response.text
    link = response.json()
    assert link["channel"] == "whatsapp"
    assert link["address"] == "+2348031234567"
    assert link["verifiedAt"] is None

    me = identity.get("/v1/account/me").json()
    assert [item["id"] for item in me["channelLinks"]] == [link["id"]]
    assert me["channelLinks"][0]["channel"] == "whatsapp"


def test_channel_link_rejects_invalid_address(
    identity: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(identity, monkeypatch)
    response = identity.post(
        "/v1/auth/channel-links", json={"channel": "sms", "address": "not-a-number"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_channel_link_conflict_notifies_the_existing_owner(
    identity: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session_factory: sessionmaker[Session],
) -> None:
    owner = _register(identity, monkeypatch, credential_id=b"owner-cred").json()["user"]
    assert (
        identity.post(
            "/v1/auth/channel-links", json={"channel": "ussd", "address": "08031234567"}
        ).status_code
        == 201
    )

    identity.cookies.clear()
    _register(identity, monkeypatch, credential_id=b"other-cred")
    conflict = identity.post(
        "/v1/auth/channel-links", json={"channel": "ussd", "address": "08031234567"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"

    with db_session_factory() as session:
        notices = session.execute(select(Notification)).scalars().all()
    assert len(notices) == 1
    assert notices[0].user_id == owner["id"]
    assert notices[0].template == "channel_link_conflict"


def test_channel_link_conflict_across_channels_notifies_the_existing_owner(
    identity: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The same number on a different channel is still one identity.

    A second account that presents the address on another channel must be
    rejected and the existing owner notified (FEAT-001 edge case).
    """
    owner = _register(identity, monkeypatch, credential_id=b"owner-cred").json()["user"]
    assert (
        identity.post(
            "/v1/auth/channel-links", json={"channel": "ussd", "address": "08031234567"}
        ).status_code
        == 201
    )

    identity.cookies.clear()
    _register(identity, monkeypatch, credential_id=b"other-cred")
    conflict = identity.post(
        "/v1/auth/channel-links", json={"channel": "whatsapp", "address": "08031234567"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"

    with db_session_factory() as session:
        notices = session.execute(select(Notification)).scalars().all()
        links = session.execute(select(ChannelLink)).scalars().all()
    assert len(notices) == 1
    assert notices[0].user_id == owner["id"]
    assert notices[0].template == "channel_link_conflict"
    # The conflicting link was never created, so the address still maps once.
    assert len(links) == 1
    assert links[0].channel == "ussd"


def test_channel_link_same_address_same_account_is_idempotent(
    identity: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session_factory: sessionmaker[Session],
) -> None:
    """A second link for the account's own address returns the existing link."""
    _register(identity, monkeypatch)
    first = identity.post(
        "/v1/auth/channel-links", json={"channel": "sms", "address": "08031234567"}
    )
    assert first.status_code == 201

    second = identity.post(
        "/v1/auth/channel-links", json={"channel": "whatsapp", "address": "08031234567"}
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["channel"] == "sms"

    with db_session_factory() as session:
        links = session.execute(select(ChannelLink)).scalars().all()
        notices = session.execute(select(Notification)).scalars().all()
    assert len(links) == 1
    assert notices == []


def test_account_endpoints_require_a_session(identity: TestClient) -> None:
    assert identity.get("/v1/account/me").status_code == 401
    assert (
        identity.post(
            "/v1/auth/channel-links", json={"channel": "sms", "address": "08031234567"}
        ).status_code
        == 401
    )


def test_options_endpoint_is_rate_limited(app: FastAPI) -> None:
    app.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1, default_window_seconds=60
    )
    with TestClient(app) as limited:
        assert limited.post("/v1/auth/login/options").status_code == 200
        blocked = limited.post("/v1/auth/login/options")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in blocked.headers


def test_phone_normalisation() -> None:
    assert normalize_phone("+234 803-123-4567") == "+2348031234567"
    assert normalize_phone("(0803) 123 4567") == "08031234567"
    assert normalize_phone("") is None
    assert normalize_phone("12345") is None
    assert normalize_phone("+2348abc") is None


def test_expired_registration_challenge_is_rejected(app: FastAPI, client: TestClient) -> None:
    store = InMemoryChallengeStore()
    past = datetime(2026, 1, 1, tzinfo=UTC) - timedelta(seconds=1)
    store.put(
        Challenge(
            id="expired",
            kind=ChallengeKind.REGISTRATION,
            challenge=b"stale",
            expires_at=past,
        )
    )
    app.state.webauthn_challenges = store
    response = client.post(
        "/v1/auth/register/verify",
        json={"challengeId": "expired", "credential": {}, "displayName": None, "locale": "en"},
    )
    assert response.status_code == 410
