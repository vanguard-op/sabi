"""Identity verification (FEAT-002, C-020..C-022).

The national identity provider is a controlled failure domain, so these tests
substitute it on ``app.state`` and assert the service's contract behaviour:
status codes, KYC transitions, the one-correction policy, queue-on-unavailable,
and that the submitted identifier never reaches the wire or the audit log.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.db.models import IdentityVerification
from app.identity import passkeys
from app.identity.verification.provider import (
    ProviderOutcome,
    ProviderResult,
    StubIdentityProvider,
    UnavailableIdentityProvider,
)
from app.identity.verification.service import mask_identifier

NIN = "12345678901"
BVN = "09876543210"


class RecordingProvider:
    """Stub that records each submitted identifier and returns a fixed outcome."""

    def __init__(self, outcome: ProviderOutcome = ProviderOutcome.MATCH) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, str]] = []

    def check(self, *, method: str, identifier: str) -> ProviderResult:
        self.calls.append((method, identifier))
        return ProviderResult(outcome=self.outcome, reference=f"{method}-ref")


@pytest.fixture
def verification(
    app: FastAPI, client: TestClient, db_session_factory: sessionmaker[Session]
) -> TestClient:
    app.state.session_factory = db_session_factory
    app.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=100, default_window_seconds=60
    )
    app.state.identity_provider = RecordingProvider()
    return client


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _register(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, *, tag: bytes = b"cred-one"
) -> str:
    options = client.post("/v1/auth/register/options", json={"locale": "en"})
    challenge_id = options.json()["challengeId"]
    verified = SimpleNamespace(
        credential_id=tag,
        credential_public_key=b"public-key",
        sign_count=0,
    )
    monkeypatch.setattr(passkeys, "verify_registration", lambda *a, **k: verified)
    response = client.post(
        "/v1/auth/register/verify",
        json={
            "challengeId": challenge_id,
            "credential": {"id": _b64(tag)},
            "displayName": "Ifeoma",
            "locale": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]["id"]


def test_submit_verified_marks_the_account_verified(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)

    response = verification.post(
        "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["verificationId"]
    assert body["status"] == "verified"

    state = verification.get("/v1/account/verification")
    assert state.status_code == 200
    assert state.json() == {"kycStatus": "verified", "method": "nin", "canCorrect": False}

    detail = verification.get(f"/v1/identity/verifications/{body['verificationId']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "verified"
    assert detail.json()["reason"] is None
    assert detail.json()["verifiedAt"].endswith("Z")


def test_submit_rejects_a_malformed_identifier_before_calling_the_provider(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    provider: RecordingProvider = verification.app.state.identity_provider

    for bad in ("123", "1234567890a", "", "  "):
        response = verification.post(
            "/v1/identity/verifications", json={"method": "nin", "identifier": bad}
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "invalid_request"

    assert provider.calls == []
    assert verification.get("/v1/account/verification").json()["kycStatus"] == "unverified"


def test_submit_requires_a_session(verification: TestClient) -> None:
    assert (
        verification.post(
            "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
        ).status_code
        == 401
    )
    assert verification.get("/v1/account/verification").status_code == 401


def test_unavailable_provider_queues_as_pending(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    verification.app.state.identity_provider = UnavailableIdentityProvider()

    response = verification.post(
        "/v1/identity/verifications", json={"method": "bvn", "identifier": BVN}
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"

    state = verification.get("/v1/account/verification")
    assert state.json()["kycStatus"] == "pending"
    assert state.json()["method"] == "bvn"
    # Discovery is never blocked by a pending check.
    assert verification.get("/v1/catalogue/search?q=x").status_code in (200, 422)


def test_pending_check_blocks_a_second_submission(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    verification.app.state.identity_provider = UnavailableIdentityProvider()

    assert (
        verification.post(
            "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
        ).status_code
        == 202
    )
    second = verification.post(
        "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_no_match_allows_one_correction_then_requires_support(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    verification.app.state.identity_provider = StubIdentityProvider(no_match={NIN, BVN})

    first = verification.post(
        "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
    )
    assert first.status_code == 202
    assert first.json()["status"] == "failed"

    rejected = verification.get("/v1/account/verification").json()
    assert rejected["kycStatus"] == "rejected"
    assert rejected["canCorrect"] is True

    detail = verification.get(f"/v1/identity/verifications/{first.json()['verificationId']}")
    assert detail.json()["reason"]
    assert detail.json()["verifiedAt"] is None

    # The one allowed correction also fails, so self-service closes.
    second = verification.post(
        "/v1/identity/verifications", json={"method": "bvn", "identifier": BVN}
    )
    assert second.status_code == 202
    assert second.json()["status"] == "failed"

    closed = verification.get("/v1/account/verification").json()
    assert closed["kycStatus"] == "rejected"
    assert closed["canCorrect"] is False

    # A third self-service attempt is refused rather than looping.
    third = verification.post(
        "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
    )
    assert third.status_code == 409
    assert third.json()["error"]["code"] == "conflict"


def test_a_correction_that_matches_marks_the_account_corrected(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    verification.app.state.identity_provider = StubIdentityProvider(no_match={NIN})

    verification.post("/v1/identity/verifications", json={"method": "nin", "identifier": NIN})
    corrected = verification.post(
        "/v1/identity/verifications", json={"method": "nin", "identifier": "11111111111"}
    )

    assert corrected.status_code == 202
    assert corrected.json()["status"] == "corrected"
    assert verification.get("/v1/account/verification").json()["kycStatus"] == "verified"


def test_unknown_or_another_accounts_verification_is_not_found(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    created = verification.post(
        "/v1/identity/verifications", json={"method": "nin", "identifier": NIN}
    ).json()

    missing = verification.get("/v1/identity/verifications/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    # A second account must not see the first account's record.
    verification.cookies.clear()
    _register(verification, monkeypatch, tag=b"cred-two")
    foreign = verification.get(f"/v1/identity/verifications/{created['verificationId']}")
    assert foreign.status_code == 404


def test_identifier_is_masked_in_storage_and_never_reaches_the_audit_log(
    verification: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session_factory: sessionmaker[Session],
) -> None:
    _register(verification, monkeypatch)
    verification.post("/v1/identity/verifications", json={"method": "nin", "identifier": NIN})

    with db_session_factory() as session:
        record = session.execute(select(IdentityVerification)).scalar_one()
    assert record.identifier_masked == mask_identifier(NIN)
    assert record.identifier_masked.endswith(NIN[-4:])
    assert NIN not in record.identifier_masked

    rendered = repr(verification.app.state.audit_log.entries())
    assert NIN not in rendered
    assert mask_identifier(NIN) not in rendered


def test_provider_receives_the_normalised_identifier_once(
    verification: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(verification, monkeypatch)
    provider: RecordingProvider = verification.app.state.identity_provider

    verification.post(
        "/v1/identity/verifications",
        json={"method": "nin", "identifier": f"  {NIN}  "},
    )

    assert provider.calls == [("nin", NIN)]
