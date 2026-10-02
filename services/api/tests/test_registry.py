"""Unit tests for the provider registry (C-013–C-016, FEAT-012).

They exercise the contract edges: operator role and MFA gates, duplicate
rejection, service ownership, amount handling, schema/component validation, the
review decisions, and the audit trail.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.access import OperatorRole
from app.core.audit import InMemoryAuditLog
from app.core.config import Settings
from app.core.errors import APIError, register_exception_handlers
from app.core.ids import new_id
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import SessionKind, SessionManager
from app.db.models import Service
from app.registry.catalogue import CLIENT_COMPONENTS, InputSchema, SchemaCatalog
from app.registry.router import router as registry_router

PROVIDER_BODY = {"name": "Lagos Water", "type": "biller", "contactEmail": "ops@lagoswater.ng"}


def _capability_body(**overrides: object) -> dict:
    body: dict = {
        "name": "Water bill",
        "inputSchemaRef": "sabi:input/service-payment",
        "amountSource": "user_entered",
        "billable": False,
        "schemaVersion": "1.0.0",
    }
    body.update(overrides)
    return body


@pytest.fixture
def app(
    settings: Settings, session_manager: SessionManager, db_session_factory: sessionmaker
) -> FastAPI:
    """A focused app mounting only the registry router.

    The modular-monolith factory discovers every module; unit tests here need
    just this module and an isolated database.
    """
    application = FastAPI()
    application.state.settings = settings
    application.state.session_factory = db_session_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1000, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    register_exception_handlers(application)
    application.include_router(registry_router, prefix="/v1")
    return application


@pytest.fixture
def api_client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def _act_as(
    client: TestClient,
    session_manager: SessionManager,
    *,
    kind: SessionKind = SessionKind.OPERATOR,
    role: str | None = OperatorRole.PROVIDER_REVIEW_ANALYST,
    mfa_verified: bool = True,
) -> None:
    token, _ = session_manager.issue(
        user_id=new_id(), kind=kind, role=role, mfa_verified=mfa_verified
    )
    client.cookies.set(session_manager.settings.session_cookie_name, token)


def _create_provider(client: TestClient, **overrides: object) -> dict:
    body = {**PROVIDER_BODY, **overrides}
    response = client.post("/v1/providers", json=body)
    assert response.status_code == 201, response.text
    return response.json()["provider"]


def _create_capability(
    client: TestClient, provider_id: str, **overrides: object
) -> tuple[int, dict]:
    response = client.post(
        f"/v1/providers/{provider_id}/capabilities", json=_capability_body(**overrides)
    )
    return response.status_code, response.json()


def _add_service(factory: sessionmaker, *, known_amount: int | None = None) -> str:
    with factory() as session:
        service = Service(
            type="biller",
            name="Lagos Water",
            collecting_body="Lagos Water Corporation",
            category="utilities",
            currency="NGN",
            known_amount=known_amount,
            status="active",
        )
        session.add(service)
        session.commit()
        return service.id


# --------------------------------------------------------------------------- #
# C-013 provider registration
# --------------------------------------------------------------------------- #
def test_provider_registration_requires_operator_role_and_mfa(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    assert api_client.post("/v1/providers", json=PROVIDER_BODY).status_code == 401

    _act_as(api_client, session_manager, mfa_verified=False)
    assert api_client.post("/v1/providers", json=PROVIDER_BODY).status_code == 403

    _act_as(api_client, session_manager, role=OperatorRole.SUPPORT_OPERATIONS_AGENT)
    assert api_client.post("/v1/providers", json=PROVIDER_BODY).status_code == 403


def test_provider_registration_returns_pending_provider(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    assert provider["status"] == "pending"
    assert provider["name"] == PROVIDER_BODY["name"]
    assert provider["type"] == "biller"
    assert provider["contactEmail"] == PROVIDER_BODY["contactEmail"]
    assert set(provider) == {"id", "name", "type", "contactEmail", "status", "createdAt"}


def test_duplicate_provider_name_is_rejected_case_insensitively(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    _create_provider(api_client, name="MTN Nigeria")
    response = api_client.post("/v1/providers", json={**PROVIDER_BODY, "name": "mtn nigeria"})
    assert response.status_code == 409


# --------------------------------------------------------------------------- #
# C-014 capability submission
# --------------------------------------------------------------------------- #
def test_capability_submission_is_pending_and_owned(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    status, body = _create_capability(api_client, provider["id"])
    assert status == 201
    capability = body["capability"]
    assert capability["status"] == "pending"
    assert capability["providerId"] == provider["id"]
    assert capability["serviceId"] is None
    assert capability["healthStatus"] == "healthy"
    assert capability["amountSource"] == "user_entered"


def test_capability_for_unknown_provider_is_404(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    status, body = _create_capability(api_client, new_id())
    assert status == 404
    assert body["error"]["code"] == "not_found"


def test_capability_with_unknown_schema_is_422(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    status, body = _create_capability(
        api_client, provider["id"], inputSchemaRef="sabi:input/not-registered"
    )
    assert status == 422
    assert body["error"]["code"] == "validation_failed"


def test_schema_needing_a_component_outside_the_catalogue_is_rejected() -> None:
    catalog = SchemaCatalog(
        [InputSchema(ref="sabi:input/hologram", components=frozenset({"hologram"}))]
    )
    assert "hologram" not in CLIENT_COMPONENTS
    with pytest.raises(APIError) as error:
        catalog.validate("sabi:input/hologram")
    assert error.value.status_code == 422
    assert error.value.details == {"components": ["hologram"]}


def test_duplicate_capability_name_for_provider_is_409(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    _create_capability(api_client, provider["id"])
    status, body = _create_capability(api_client, provider["id"], name="Water bill")
    assert status == 409
    assert body["error"]["code"] == "conflict"


def test_service_claimed_by_another_provider_is_409(
    api_client: TestClient,
    session_manager: SessionManager,
    db_session_factory: sessionmaker,
) -> None:
    _act_as(api_client, session_manager)
    service_id = _add_service(db_session_factory)
    first = _create_provider(api_client, name="Provider One")
    second = _create_provider(api_client, name="Provider Two")

    status, _ = _create_capability(api_client, first["id"], serviceId=service_id)
    assert status == 201

    status, body = _create_capability(
        api_client, second["id"], serviceId=service_id, name="Water bill two"
    )
    assert status == 409
    assert "claimed" in body["error"]["message"]


def test_amount_handling_rejects_a_fixed_amount_without_a_stated_value(
    api_client: TestClient,
    session_manager: SessionManager,
    db_session_factory: sessionmaker,
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    service_id = _add_service(db_session_factory, known_amount=None)

    status, body = _create_capability(
        api_client, provider["id"], serviceId=service_id, amountSource="fixed"
    )
    assert status == 422
    assert "minor units" in body["error"]["message"]


def test_amount_handling_accepts_a_fixed_amount_in_minor_units(
    api_client: TestClient,
    session_manager: SessionManager,
    db_session_factory: sessionmaker,
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    service_id = _add_service(db_session_factory, known_amount=500_00)
    status, _ = _create_capability(
        api_client, provider["id"], serviceId=service_id, amountSource="fixed"
    )
    assert status == 201


def test_billable_capability_needs_a_price(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    status, _ = _create_capability(api_client, provider["id"], billable=True)
    assert status == 422

    status, _ = _create_capability(
        api_client,
        provider["id"],
        billable=True,
        priceAmount=100_00,
        priceCurrency="NGN",
    )
    assert status == 201


def test_non_billable_capability_cannot_carry_a_price(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    status, _ = _create_capability(
        api_client, provider["id"], billable=False, priceAmount=100_00, priceCurrency="NGN"
    )
    assert status == 422


# --------------------------------------------------------------------------- #
# C-015 capability read
# --------------------------------------------------------------------------- #
def test_capability_read_requires_a_session(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    _, body = _create_capability(api_client, provider["id"])
    capability_id = body["capability"]["id"]

    api_client.cookies.clear()
    assert api_client.get(f"/v1/capabilities/{capability_id}").status_code == 401


def test_capability_read_returns_health_status(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    _, body = _create_capability(api_client, provider["id"])
    capability_id = body["capability"]["id"]

    # An end-user session is enough for the internal read surface; the review
    # surface additionally requires the operator role and MFA (C-015).
    _act_as(api_client, session_manager, kind=SessionKind.USER, role=None, mfa_verified=False)
    response = api_client.get(f"/v1/capabilities/{capability_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["healthStatus"] == "healthy"
    assert payload["capability"]["id"] == capability_id


def test_capability_read_unknown_is_404(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    assert api_client.get(f"/v1/capabilities/{new_id()}").status_code == 404


# --------------------------------------------------------------------------- #
# C-016 capability review
# --------------------------------------------------------------------------- #
def _submit_capability(
    api_client: TestClient, session_manager: SessionManager, **overrides: object
) -> dict:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    _, body = _create_capability(api_client, provider["id"], **overrides)
    return body["capability"]


def test_review_requires_operator_role_and_mfa(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    capability = _submit_capability(api_client, session_manager)
    url = f"/v1/capabilities/{capability['id']}/review"
    payload = {"decision": "approve", "schemaVersion": "1.0.0"}

    api_client.cookies.clear()
    assert api_client.post(url, json=payload).status_code == 401

    _act_as(api_client, session_manager, mfa_verified=False)
    assert api_client.post(url, json=payload).status_code == 403


def test_review_approve_activates_capability_and_claims_service(
    api_client: TestClient,
    session_manager: SessionManager,
    db_session_factory: sessionmaker,
) -> None:
    _act_as(api_client, session_manager)
    service_id = _add_service(db_session_factory, known_amount=500_00)
    provider = _create_provider(api_client)
    _, body = _create_capability(
        api_client, provider["id"], serviceId=service_id, amountSource="fixed"
    )
    capability_id = body["capability"]["id"]

    response = api_client.post(
        f"/v1/capabilities/{capability_id}/review",
        json={
            "decision": "approve",
            "reason": "Authority and schema verified.",
            "schemaVersion": "1.0.0",
        },
    )
    assert response.status_code == 200
    reviewed = response.json()["capability"]
    assert reviewed["status"] == "active"
    assert reviewed["healthStatus"] == "healthy"

    with db_session_factory() as session:
        service = session.get(Service, service_id)
        assert service.provider_id == provider["id"]
        assert service.capability_id == capability_id


def test_review_reject_withdraws_capability(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    capability = _submit_capability(api_client, session_manager)
    response = api_client.post(
        f"/v1/capabilities/{capability['id']}/review",
        json={
            "decision": "reject",
            "reason": "Authority not established.",
            "schemaVersion": "1.0.0",
        },
    )
    assert response.status_code == 200
    assert response.json()["capability"]["status"] == "withdrawn"


def test_review_quarantine_marks_capability_unavailable(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    capability = _submit_capability(api_client, session_manager)
    response = api_client.post(
        f"/v1/capabilities/{capability['id']}/review",
        json={"decision": "quarantine", "reason": "Forged result.", "schemaVersion": "1.0.0"},
    )
    assert response.status_code == 200
    reviewed = response.json()["capability"]
    assert reviewed["status"] == "quarantined"
    assert reviewed["healthStatus"] == "unavailable"


def test_review_deregister_withdraws_provider_capabilities(
    api_client: TestClient,
    session_manager: SessionManager,
    db_session_factory: sessionmaker,
) -> None:
    from app.db.models import Provider

    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    _, first = _create_capability(api_client, provider["id"], name="Water bill")
    _, second = _create_capability(api_client, provider["id"], name="Water arrears")

    api_client.post(
        f"/v1/capabilities/{first['capability']['id']}/review",
        json={"decision": "approve", "schemaVersion": "1.0.0"},
    )
    response = api_client.post(
        f"/v1/capabilities/{first['capability']['id']}/review",
        json={"decision": "deregister", "reason": "Provider withdrawn.", "schemaVersion": "1.0.0"},
    )
    # The first capability was already active, so it is no longer pending.
    assert response.status_code == 409

    # Deregister while the second is still pending.
    response = api_client.post(
        f"/v1/capabilities/{second['capability']['id']}/review",
        json={"decision": "deregister", "reason": "Provider withdrawn.", "schemaVersion": "1.0.0"},
    )
    assert response.status_code == 200
    assert response.json()["capability"]["status"] == "withdrawn"

    with db_session_factory() as session:
        assert session.get(Provider, provider["id"]).status == "deregistered"


def test_review_non_pending_capability_is_409(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    capability = _submit_capability(api_client, session_manager)
    url = f"/v1/capabilities/{capability['id']}/review"
    approve = {"decision": "approve", "schemaVersion": "1.0.0"}
    assert api_client.post(url, json=approve).status_code == 200
    assert api_client.post(url, json=approve).status_code == 409


def test_review_schema_version_mismatch_is_409(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    capability = _submit_capability(api_client, session_manager)
    response = api_client.post(
        f"/v1/capabilities/{capability['id']}/review",
        json={"decision": "approve", "schemaVersion": "9.9.9"},
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #
def test_privileged_actions_are_audited_without_personal_data(
    app: FastAPI, api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    provider = _create_provider(api_client)
    _, body = _create_capability(api_client, provider["id"])
    api_client.post(
        f"/v1/capabilities/{body['capability']['id']}/review",
        json={"decision": "approve", "reason": "Verified.", "schemaVersion": "1.0.0"},
    )

    entries = app.state.audit_log.entries()
    actions = [entry.action for entry in entries]
    assert actions == ["provider.create", "capability.create", "capability.review"]

    rendered = " ".join(f"{entry.material()}" for entry in entries)
    assert PROVIDER_BODY["contactEmail"] not in rendered
    review = entries[-1]
    assert review.actor_role == OperatorRole.PROVIDER_REVIEW_ANALYST
    assert review.detail["toStatus"] == "active"
    assert review.detail["schemaVersion"] == "1.0.0"
