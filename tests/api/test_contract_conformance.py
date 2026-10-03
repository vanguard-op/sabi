"""API-service contract conformance (C-001 to C-016).

This is the integration check the per-module unit suites do not make: that the
assembled API service actually mounts the whole frozen contract set the client was
built against, and that every error path uses the one shared envelope.

The agent paths (C-009, C-012) are part of that set: architecture.md makes the
gateway the client's sole entry point, so the client's contract is the gateway
surface, not the private AI service. They are mounted and checked here.

Reference: CONTRACTS.md, DELIVERY.md conventions.
"""

from __future__ import annotations

from pathlib import Path

# Every path in CONTRACTS.md that the API service owns. The agent paths are
# served by the gateway module, which forwards to the AI service (D-021).
API_CONTRACT_PATHS = {
    "/v1/auth/register/options",
    "/v1/auth/register/verify",
    "/v1/auth/login/options",
    "/v1/auth/login/verify",
    "/v1/auth/recovery/verify",
    "/v1/auth/recovery/regenerate",
    "/v1/auth/channel-links",
    "/v1/account/me",
    "/v1/agent/intents",
    "/v1/catalogue/search",
    "/v1/catalogue/services/{serviceId}",
    "/v1/agent/surfaces",
    "/v1/providers",
    "/v1/providers/{providerId}/capabilities",
    "/v1/capabilities/{capabilityId}",
    "/v1/capabilities/{capabilityId}/review",
}

# The Phase 2 payment loop, all reached through the gateway. The payment
# operations (C-017..C-019, C-029) are forwarded to the isolated payment module;
# the rest are owned by the assembled API service.
PHASE2_CONTRACT_PATHS = {
    "/v1/payments/authorise",
    "/v1/payments/{paymentId}/execute",
    "/v1/payments",
    "/v1/payments/{paymentId}/refund",
    "/v1/identity/verifications",
    "/v1/identity/verifications/{verificationId}",
    "/v1/account/verification",
    "/v1/receipts",
    "/v1/receipts/{receiptId}",
    "/v1/receipts/{receiptId}/document",
    "/v1/cases",
    "/v1/cases/{caseId}",
    "/v1/cases/{caseId}/dispute",
    "/v1/payments/federal/prepare",
    "/v1/payments/federal/{paymentId}/receipt",
    "/v1/payments/federal/{paymentId}/reconcile",
    "/v1/payments/bills/validate",
    "/v1/payments/bills",
    "/v1/payments/bills/{paymentId}/token",
    "/v1/channels/ussd/session",
    "/v1/channels/ussd/authorise",
    "/v1/channels/sms/status/{reference}",
}


def test_api_service_mounts_every_owned_contract_path(api_app) -> None:
    paths = set(api_app.openapi()["paths"])
    missing = API_CONTRACT_PATHS - paths
    assert not missing, f"API service is missing contract paths: {sorted(missing)}"


def test_api_service_mounts_every_phase2_contract_path(api_app) -> None:
    """The whole payment-loop contract set is mounted on the assembled service."""

    paths = set(api_app.openapi()["paths"])
    missing = PHASE2_CONTRACT_PATHS - paths
    assert not missing, f"API service is missing Phase 2 contract paths: {sorted(missing)}"


def test_unauthenticated_requests_use_the_shared_error_envelope(api_client) -> None:
    """401s on protected surfaces carry the one envelope and code the client maps."""

    for path, method in (
        ("/v1/account/me", "get"),
        ("/v1/auth/channel-links", "post"),
        ("/v1/auth/recovery/regenerate", "post"),
        ("/v1/agent/intents", "post"),
        ("/v1/agent/surfaces", "post"),
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


# --------------------------------------------------------------------------- #
# Phase gate wiring: the integration layer must actually be run by the pipeline.
# --------------------------------------------------------------------------- #


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_integration_suite_is_a_documented_and_pipeline_enforced_target() -> None:
    """D-023: tests/** gates, so the pipeline must run it.

    The cross-service suite proves the delivered whole; if no command or CI job
    invokes it, the gate is advisory. This guards the wiring itself so it cannot
    silently regress: a `test-integration` target exists and CI calls it.
    """

    makefile = (_repo_root() / "Makefile").read_text(encoding="utf-8")
    assert "test-integration:" in makefile, "Makefile must expose a test-integration target"
    assert "tests/api" in makefile and "tests/ai" in makefile, (
        "the test-integration target must run both integration directories"
    )

    ci = (_repo_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "make test-integration" in ci, "CI must run the integration gate"
    # And it must be a blocking job, not continue-on-error like the MQ report.
    integration_job = ci.split("integration gate", 1)[1]
    assert "continue-on-error: true" not in integration_job.split("model-quality", 1)[0], (
        "the integration gate must block, not report-and-continue"
    )


def test_model_quality_bar_remains_reported_where_it_cannot_be_measured() -> None:
    """MQ-001/002/003 need golden datasets and judges the delivery does not carry.

    The bar is not silently dropped: the attestation test keeps the gap explicit
    and a non-blocking pipeline job reports it every run, so an accepted
    disposition stays visible rather than reading as a pass.
    """

    attestation = (_repo_root() / "tests" / "ai" / "test_model_quality_attestation.py").read_text(
        encoding="utf-8"
    )
    assert "pytest.fail" in attestation, (
        "the MQ attestation must fail to surface the unmeasured bar, not assert a pass"
    )

    ci = (_repo_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "make test-model-quality" in ci, "CI must report the model-quality attestation"
