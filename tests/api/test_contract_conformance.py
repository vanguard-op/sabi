"""API-service contract conformance (C-001 to C-008, C-010, C-011, C-013 to C-016).

This is the integration check the per-module unit suites do not make: that the
assembled API service actually mounts the whole frozen contract set the client was
built against, and that every error path uses the one shared envelope.

Reference: CONTRACTS.md, DELIVERY.md conventions.
"""

from __future__ import annotations

# Every path in CONTRACTS.md that the API service owns.
API_CONTRACT_PATHS = {
    "/v1/auth/register/options",
    "/v1/auth/register/verify",
    "/v1/auth/login/options",
    "/v1/auth/login/verify",
    "/v1/auth/recovery/verify",
    "/v1/auth/recovery/regenerate",
    "/v1/auth/channel-links",
    "/v1/account/me",
    "/v1/catalogue/search",
    "/v1/catalogue/services/{serviceId}",
    "/v1/providers",
    "/v1/providers/{providerId}/capabilities",
    "/v1/capabilities/{capabilityId}",
    "/v1/capabilities/{capabilityId}/review",
}


def test_api_service_mounts_every_owned_contract_path(api_app) -> None:
    paths = set(api_app.openapi()["paths"])
    missing = API_CONTRACT_PATHS - paths
    assert not missing, f"API service is missing contract paths: {sorted(missing)}"


def test_unauthenticated_requests_use_the_shared_error_envelope(api_client) -> None:
    """401s on protected surfaces carry the one envelope and code the client maps."""

    for path, method in (
        ("/v1/account/me", "get"),
        ("/v1/auth/channel-links", "post"),
        ("/v1/auth/recovery/regenerate", "post"),
        ("/v1/providers", "post"),
        ("/v1/catalogue/search", "get"),
    ):
        response = getattr(api_client, method)(path)
        assert response.status_code == 401, f"{method} {path}: {response.status_code}"
        body = response.json()
        assert set(body) == {"error"}
        error = body["error"]
        assert set(error) <= {"code", "message", "details"}
        assert error["code"] == "unauthenticated"
        assert isinstance(error["message"], str) and error["message"]


def test_validation_failure_returns_the_envelope_not_a_framework_body(api_client) -> None:
    """A bad body returns the shared envelope, never the framework's default shape."""

    # Registration options is public, so the bad body reaches validation directly.
    response = api_client.post("/v1/auth/register/options", json={"locale": "fr"})
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_request"

    # A structurally invalid body on a public surface is still enveloped.
    malformed = api_client.post("/v1/auth/register/options", json={})
    assert malformed.status_code in {400, 422}
    assert set(malformed.json()) == {"error"}


def test_provider_registration_wire_shape_is_camel_case(
    api_client, session_manager, sign_in_as
) -> None:
    from app.core.access import OperatorRole
    from app.core.sessions import SessionKind

    sign_in_as(
        api_client,
        session_manager,
        kind=SessionKind.OPERATOR,
        role=OperatorRole.PROVIDER_REVIEW_ANALYST,
        mfa_verified=True,
    )
    response = api_client.post(
        "/v1/providers",
        json={"name": "Lagos Water", "type": "biller", "contactEmail": "ops@lagoswater.ng"},
    )
    assert response.status_code == 201, response.text
    provider = response.json()["provider"]
    assert set(provider) == {"id", "name", "type", "contactEmail", "status", "createdAt"}
    assert "contact_email" not in provider
    assert provider["status"] == "pending"


def test_capability_read_returns_health_status_alongside_the_capability(
    api_client, session_manager, sign_in_as, db_session_factory
) -> None:
    from app.core.access import OperatorRole
    from app.core.sessions import SessionKind

    sign_in_as(
        api_client,
        session_manager,
        kind=SessionKind.OPERATOR,
        role=OperatorRole.PROVIDER_REVIEW_ANALYST,
        mfa_verified=True,
    )
    provider = api_client.post(
        "/v1/providers",
        json={"name": "MTN", "type": "aggregator", "contactEmail": "ops@mtn.ng"},
    ).json()["provider"]

    created = api_client.post(
        f"/v1/providers/{provider['id']}/capabilities",
        json={
            "name": "Airtime",
            "inputSchemaRef": "sabi:input/service-payment",
            "amountSource": "user_entered",
            "billable": False,
            "schemaVersion": "1.0.0",
        },
    )
    assert created.status_code == 201, created.text
    capability_id = created.json()["capability"]["id"]

    found = api_client.get(f"/v1/capabilities/{capability_id}")
    assert found.status_code == 200
    body = found.json()
    assert set(body) == {"capability", "healthStatus"}
    assert body["healthStatus"] in {"healthy", "degraded", "unavailable"}
    assert body["capability"]["status"] == "pending"
