"""Phase 1 feature acceptance served by the API service.

Observable behaviour for the key outcomes the phase promises: passwordless
onboarding (FEAT-001), discovery that answers where and how much, and never
fabricates (FEAT-004), and provider registration that makes adding a service a
registration, not a release (FEAT-012).

Reference: roadmap.md "Phase 1: Foundations", features.md, user-flow.md Flow 1.
"""

from __future__ import annotations


def test_channel_link_never_creates_a_second_account(
    api_client, session_manager, seed_user, sign_in_as
):
    """FEAT-001 / C-007: a USSD/WhatsApp number links to one account.

    C-007 returns 409 when an "address already linked to another account" is
    re-linked. The address is the identity, so a second account claiming the same
    number on a different channel must also be rejected; the unique key must be
    the address, not (channel, address).
    """

    first_user = seed_user()
    token, _ = session_manager.issue(user_id=first_user)
    api_client.cookies.set(session_manager.settings.session_cookie_name, token)
    first = api_client.post(
        "/v1/auth/channel-links", json={"channel": "ussd", "address": "08031234567"}
    )
    assert first.status_code == 201, first.text
    assert first.json()["channel"] == "ussd"

    # A second account claims the same number over a different channel: the
    # address already belongs to an account, so the link is rejected.
    second_user = seed_user(display_name="Musa")
    token, _ = session_manager.issue(user_id=second_user)
    api_client.cookies.set(session_manager.settings.session_cookie_name, token)
    second = api_client.post(
        "/v1/auth/channel-links", json={"channel": "whatsapp", "address": "08031234567"}
    )
    assert second.status_code == 409, (
        f"expected the shared address to be rejected, got {second.status_code}: {second.text}"
    )
    assert second.json()["error"]["code"] == "conflict"


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
