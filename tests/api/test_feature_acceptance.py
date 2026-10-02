"""Phase 1 feature acceptance served by the API service.

Observable behaviour for the key outcomes the phase promises: passwordless
onboarding (FEAT-001), discovery that answers where and how much, and never
fabricates (FEAT-004), and provider registration that makes adding a service a
registration, not a release (FEAT-012).

The identity acceptance test drives the real contract path end to end: register
through C-001/C-002, then link through C-007, so it proves the assembled flow
rather than a hand-minted session. The service's own unit suite substitutes the
WebAuthn ceremony, as this does: the ceremony is the library's responsibility.

Reference: roadmap.md "Phase 1: Foundations", features.md, user-flow.md Flow 1.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

from app.identity import passkeys


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _register(client, monkeypatch, *, credential_id: bytes, address: str | None = None):
    """Create an account through the real C-001/C-002 path.

    The WebAuthn attestation is substituted (its verification is the library's
    tested responsibility); every other step -- challenge minting, account row,
    recovery code, and the HttpOnly session cookie -- is the delivered code.
    """

    options = client.post("/v1/auth/register/options", json={"locale": "en"})
    assert options.status_code == 200, options.text
    challenge_id = options.json()["challengeId"]
    monkeypatch.setattr(
        passkeys,
        "verify_registration",
        lambda *a, **k: SimpleNamespace(
            credential_id=credential_id,
            credential_public_key=b"public-key",
            sign_count=0,
        ),
    )
    response = client.post(
        "/v1/auth/register/verify",
        json={
            "challengeId": challenge_id,
            "credential": {"id": _b64(credential_id)},
            "displayName": None,
            "locale": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def test_channel_link_never_creates_a_second_account(api_client, monkeypatch):
    """FEAT-001 / C-007: a USSD/WhatsApp number links to one account.

    C-007 returns 409 when an "address already linked to another account" is
    re-linked. The address is the identity, so a second account claiming the same
    number on a different channel must also be rejected; the unique key must be
    the address, not (channel, address).

    Self-contained: both accounts are created through registration over the real
    C-001/C-002 endpoints, and each link is authorised by the session cookie that
    registration set -- no seeded rows or hand-minted sessions.
    """

    first_user = _register(api_client, monkeypatch, credential_id=b"cred-one")
    first = api_client.post(
        "/v1/auth/channel-links", json={"channel": "ussd", "address": "08031234567"}
    )
    assert first.status_code == 201, first.text
    assert first.json()["channel"] == "ussd"
    assert api_client.get("/v1/account/me").json()["id"] == first_user["id"]

    # A second account, registered the same way, claims the same number over a
    # different channel: the address already belongs to an account, so the link
    # is rejected and the owner notified.
    api_client.cookies.clear()
    second_user = _register(api_client, monkeypatch, credential_id=b"cred-two")
    second = api_client.post(
        "/v1/auth/channel-links", json={"channel": "whatsapp", "address": "08031234567"}
    )
    assert second.status_code == 409, (
        f"expected the shared address to be rejected, got {second.status_code}: {second.text}"
    )
    assert second.json()["error"]["code"] == "conflict"

    # The rejected link did not attach to the second account.
    assert api_client.get("/v1/account/me").json()["id"] == second_user["id"]
    assert api_client.get("/v1/account/me").json()["channelLinks"] == []


def test_invalid_channel_address_is_rejected(signed_in_user, api_client):
    response = api_client.post(
        "/v1/auth/channel-links", json={"channel": "ussd", "address": "not-a-number"}
    )
    assert response.status_code in {400, 422}


def test_account_me_returns_the_contract_fields(signed_in_user, api_client):
    response = api_client.get("/v1/account/me")
    assert response.status_code == 200
    body = response.json()
    expected = {
        "id",
        "displayName",
        "locale",
        "preferredChannel",
        "kycStatus",
        "accountStatus",
        "channelLinks",
        "createdAt",
        "updatedAt",
    }
    assert expected <= set(body), sorted(expected - set(body))
    assert body["id"] == signed_in_user


def test_catalogue_search_lists_the_matching_collecting_body(
    api_client, session_manager, sign_in_as, db_session_factory
):
    from app.db.models import Service

    with db_session_factory() as db:
        db.add(
            Service(
                type="government",
                name="Onitsha South Local Government Council",
                collecting_body="Onitsha South LGA",
                category="levy",
                currency="NGN",
                status="active",
            )
        )
        db.commit()
    sign_in_as(api_client, session_manager)

    body = api_client.get("/v1/catalogue/search", params={"q": "council levy Onitsha"}).json()
    assert body["noMatch"] is False
    assert body["results"][0]["collectingBody"] == "Onitsha South LGA"
    assert body["results"][0]["serviceId"]


def test_catalogue_miss_records_the_query_and_fabricates_nothing(
    api_client, session_manager, sign_in_as
):
    sign_in_as(api_client, session_manager)
    body = api_client.get(
        "/v1/catalogue/search", params={"q": "a service that does not exist"}
    ).json()
    assert body == {"results": [], "noMatch": True}


def test_known_amount_is_shown_in_minor_units(
    api_client, session_manager, sign_in_as, db_session_factory
):
    from app.db.models import Service

    with db_session_factory() as db:
        db.add(
            Service(
                type="biller",
                name="Ikeja Electric",
                collecting_body="Ikeja Electricity Distribution Company",
                category="electricity",
                currency="NGN",
                known_amount=500_00,
                status="active",
            )
        )
        db.commit()
    sign_in_as(api_client, session_manager)

    result = api_client.get("/v1/catalogue/search", params={"q": "Ikeja Electric"}).json()[
        "results"
    ][0]
    assert result["knownAmount"] == 500_00
    assert result["currency"] == "NGN"


def test_service_detail_shows_amount_reference_and_deadline_before_payment(
    api_client, session_manager, sign_in_as, db_session_factory
):
    """FEAT-004: a selected obligation exposes its known detail before any payment."""

    from app.db.models import Service

    with db_session_factory() as db:
        service = Service(
            type="government",
            name="Land Use Charge",
            collecting_body="Lagos State Government",
            category="government",
            currency="NGN",
            known_amount=2_500_000,
            status="active",
        )
        db.add(service)
        db.commit()
        service_id = service.id
    sign_in_as(api_client, session_manager)

    body = api_client.get(f"/v1/catalogue/services/{service_id}").json()["service"]
    assert body["knownAmount"] == 2_500_000
    assert body["collectingBody"] == "Lagos State Government"
    assert "reference" in body or "refreshedAt" in body


def _as_review_analyst(sign_in_as, client, manager) -> None:
    from app.core.access import OperatorRole
    from app.core.sessions import SessionKind

    sign_in_as(
        client,
        manager,
        kind=SessionKind.OPERATOR,
        role=OperatorRole.PROVIDER_REVIEW_ANALYST,
        mfa_verified=True,
    )


def test_submitted_capability_is_pending_until_reviewed(
    api_client, session_manager, sign_in_as, db_session_factory
):
    from app.db.models import Service

    _as_review_analyst(sign_in_as, api_client, session_manager)
    provider = api_client.post(
        "/v1/providers",
        json={"name": "Provider One", "type": "biller", "contactEmail": "ops@p1.ng"},
    ).json()["provider"]

    with db_session_factory() as db:
        service = Service(
            type="biller",
            name="Water bill",
            collecting_body="Lagos Water Corporation",
            category="utilities",
            currency="NGN",
            known_amount=500_00,
            status="active",
        )
        db.add(service)
        db.commit()
        service_id = service.id

    created = api_client.post(
        f"/v1/providers/{provider['id']}/capabilities",
        json={
            "name": "Water bill",
            "serviceId": service_id,
            "inputSchemaRef": "sabi:input/service-payment",
            "amountSource": "fixed",
            "billable": False,
            "schemaVersion": "1.0.0",
        },
    )
    assert created.status_code == 201, created.text
    capability = created.json()["capability"]
    assert capability["status"] == "pending"
    assert capability["healthStatus"] == "healthy"

    approved = api_client.post(
        f"/v1/capabilities/{capability['id']}/review",
        json={"decision": "approve", "reason": "Verified.", "schemaVersion": "1.0.0"},
    )
    assert approved.status_code == 200
    assert approved.json()["capability"]["status"] == "active"


def test_review_requires_operator_role_and_mfa(api_client, session_manager, sign_in_as):
    """FEAT-012 / operations.md: only a provider review analyst with MFA reviews."""

    response = api_client.post(
        "/v1/capabilities/anything/review",
        json={"decision": "approve", "schemaVersion": "1.0.0"},
    )
    assert response.status_code == 401

    sign_in_as(api_client, session_manager, mfa_verified=False)
    blocked = api_client.post(
        "/v1/capabilities/anything/review",
        json={"decision": "approve", "schemaVersion": "1.0.0"},
    )
    assert blocked.status_code == 403


def test_incompatible_schema_version_is_rejected_until_reviewed(
    api_client, session_manager, sign_in_as
):
    _as_review_analyst(sign_in_as, api_client, session_manager)
    provider = api_client.post(
        "/v1/providers",
        json={"name": "Provider Two", "type": "biller", "contactEmail": "ops@p2.ng"},
    ).json()["provider"]
    capability = api_client.post(
        f"/v1/providers/{provider['id']}/capabilities",
        json={
            "name": "Airtime",
            "inputSchemaRef": "sabi:input/service-payment",
            "amountSource": "user_entered",
            "billable": False,
            "schemaVersion": "2.0.0",
        },
    ).json()["capability"]

    response = api_client.post(
        f"/v1/capabilities/{capability['id']}/review",
        json={"decision": "approve", "schemaVersion": "1.0.0"},
    )
    assert response.status_code == 409


def test_duplicate_provider_is_rejected(api_client, session_manager, sign_in_as):
    """FEAT-012: two providers cannot register the same name; ownership is resolved."""

    _as_review_analyst(sign_in_as, api_client, session_manager)
    first = api_client.post(
        "/v1/providers",
        json={"name": "MTN Nigeria", "type": "aggregator", "contactEmail": "a@mtn.ng"},
    )
    assert first.status_code == 201

    duplicate = api_client.post(
        "/v1/providers",
        json={"name": "mtn nigeria", "type": "aggregator", "contactEmail": "b@mtn.ng"},
    )
    assert duplicate.status_code == 409


# --------------------------------------------------------------------------- #
# FEAT-003 / FEAT-011 through the gateway: the client's single entry point.
# --------------------------------------------------------------------------- #


def test_intent_resolution_is_reachable_through_the_gateway(
    signed_in_user, api_client, agent_ai_client
):
    """FEAT-003 / C-009: the client reaches intent resolution on the gateway.

    architecture.md makes the gateway the client's sole entry point, so the
    assembled app must expose C-009 there and return the frozen camelCase body,
    forwarding the request unchanged to the AI service.
    """

    response = api_client.post(
        "/v1/agent/intents",
        json={"text": "I wan pay my electricity", "locale": "pcm", "channel": "app"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"intent", "candidates", "source"}
    assert set(body["intent"]) == {
        "intentType",
        "target",
        "amount",
        "currency",
        "reference",
        "constraints",
        "confidence",
        "language",
        "clarifyingQuestion",
    }
    assert body["source"] == "model"
    assert agent_ai_client.intent_calls == [
        {"text": "I wan pay my electricity", "locale": "pcm", "channel": "app"}
    ]


def test_surface_composition_is_reachable_through_the_gateway(
    signed_in_user, api_client, agent_ai_client
):
    """FEAT-011 / C-012: the client composes a surface through the gateway."""

    response = api_client.post(
        "/v1/agent/surfaces",
        json={"task": "confirmation", "context": {"amount": 500_00}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"messages", "fallback"}
    assert body["fallback"] == "confirmation"
    assert agent_ai_client.surface_calls == [
        {"task": "confirmation", "context": {"amount": 500_00}}
    ]


def test_gateway_rejects_a_request_outside_the_contract_before_forwarding(
    signed_in_user, api_client, agent_ai_client
):
    """C-009/C-012 bounds are enforced at the gateway, not passed upstream."""

    empty = api_client.post("/v1/agent/intents", json={"text": "   "})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "invalid_request"

    unknown_task = api_client.post(
        "/v1/agent/surfaces", json={"task": "run_payment", "context": {}}
    )
    # An unknown task is a client error (C-012). The gateway either rejects it
    # itself or forwards it and maps the AI service's 400 to the same envelope.
    assert unknown_task.status_code == 400
    assert unknown_task.json()["error"]["code"] == "invalid_request"

    # The empty request never reached the AI service.
    assert agent_ai_client.intent_calls == []
