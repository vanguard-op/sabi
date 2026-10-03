"""Unit tests for the privileged-action audit view (C-041-C-043, FEAT-012).

They exercise the contract edges: the role and MFA gates on each route, the read
filters and keyset pagination, that the read leaves the append-only log
untouched, the finding state rule, and the export window bound. The endpoints are
mounted on a focused app with an isolated store, following the registry tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.audit.models import AuditExport, ComplianceFinding
from app.audit.router import router as audit_router
from app.core.access import OperatorRole
from app.core.audit import GENESIS_HASH, InMemoryAuditLog, build_entry
from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.core.ids import new_id
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter
from app.core.sessions import SessionKind, SessionManager
from app.core.time import to_rfc3339, utcnow

READ_URL = "/v1/staff/audit"


@pytest.fixture
def app(
    settings: Settings, session_manager: SessionManager, db_session_factory: sessionmaker
) -> FastAPI:
    application = FastAPI()
    application.state.settings = settings
    application.state.session_factory = db_session_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1000, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    register_exception_handlers(application)
    application.include_router(audit_router, prefix="/v1")
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
    role: str | None = OperatorRole.COMPLIANCE_PRIVACY_OFFICER,
    mfa_verified: bool = True,
) -> str:
    user_id = new_id()
    token, _ = session_manager.issue(
        user_id=user_id, kind=kind, role=role, mfa_verified=mfa_verified
    )
    client.cookies.set(session_manager.settings.session_cookie_name, token)
    return user_id


def _seed_entry(audit: InMemoryAuditLog, action: str, **overrides: object):
    return audit.append(action, **overrides)


class SeededAuditLog(InMemoryAuditLog):
    """An in-memory log that also lets a test pin an entry's timestamp."""

    def seed(self, action: str, *, occurred_at, **overrides: object):
        with self._lock:
            prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
            entry = build_entry(
                sequence=len(self._entries) + 1,
                prev_hash=prev_hash,
                action=action,
                occurred_at=occurred_at,
                **overrides,
            )
            self._entries.append(entry)
            return entry


def _open_finding(
    db_session_factory: sessionmaker[Session],
    *,
    blocked_role: str | None = "support_operations_agent",
) -> ComplianceFinding:
    with db_session_factory() as session:
        finding = ComplianceFinding(
            id=new_id(),
            target="op-42",
            blocked_role=blocked_role,
            summary="No entry for this action.",
            status="open",
            opened_at=utcnow(),
        )
        session.add(finding)
        session.commit()
        return finding


# --------------------------------------------------------------------------- #
# C-041 audit read
# --------------------------------------------------------------------------- #
def test_audit_read_requires_operator_role_and_mfa(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    assert api_client.get(READ_URL).status_code == 401

    _act_as(api_client, session_manager, mfa_verified=False)
    assert api_client.get(READ_URL).status_code == 403

    _act_as(api_client, session_manager, role=OperatorRole.SUPPORT_OPERATIONS_AGENT)
    assert api_client.get(READ_URL).status_code == 403

    _act_as(api_client, session_manager, kind=SessionKind.USER, role=None)
    assert api_client.get(READ_URL).status_code == 403


def test_audit_read_allows_compliance_officer_and_administrator(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager, role=OperatorRole.COMPLIANCE_PRIVACY_OFFICER)
    assert api_client.get(READ_URL).status_code == 200

    _act_as(api_client, session_manager, role=OperatorRole.ADMINISTRATOR)
    assert api_client.get(READ_URL).status_code == 200


def test_audit_read_returns_newest_first_with_camel_case_fields(
    api_client: TestClient, session_manager: SessionManager, app: FastAPI
) -> None:
    _act_as(api_client, session_manager)
    _seed_entry(app.state.audit_log, "provider.create", actor_id="op-1", actor_role="analyst")
    _seed_entry(
        app.state.audit_log,
        "capability.quarantine",
        actor_id="op-2",
        actor_role="compliance_privacy_officer",
        target="cap-9",
        reason="forged result",
    )

    response = api_client.get(READ_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["nextCursor"] is None
    assert [entry["action"] for entry in body["entries"]] == [
        "capability.quarantine",
        "provider.create",
    ]
    newest = body["entries"][0]
    assert set(newest) == {"auditId", "actor", "role", "target", "action", "reason", "occurredAt"}
    assert newest["actor"] == "op-2"
    assert newest["role"] == "compliance_privacy_officer"
    assert newest["target"] == "cap-9"
    assert newest["occurredAt"].endswith("Z")


def test_audit_read_filters_by_actor_role_target_and_action(
    api_client: TestClient, session_manager: SessionManager, app: FastAPI
) -> None:
    _act_as(api_client, session_manager)
    _seed_entry(app.state.audit_log, "provider.create", actor_id="op-1", actor_role="analyst")
    _seed_entry(
        app.state.audit_log,
        "capability.quarantine",
        actor_id="op-2",
        actor_role="officer",
        target="cap-9",
    )
    _seed_entry(
        app.state.audit_log,
        "capability.approve",
        actor_id="op-2",
        actor_role="officer",
        target="cap-9",
    )

    def actions(**params: str) -> list[str]:
        response = api_client.get(READ_URL, params=params)
        assert response.status_code == 200
        return [entry["action"] for entry in response.json()["entries"]]

    assert actions(actor="op-2") == ["capability.approve", "capability.quarantine"]
    assert actions(role="analyst") == ["provider.create"]
    assert actions(target="cap-9") == ["capability.approve", "capability.quarantine"]
    assert actions(action="capability.quarantine") == ["capability.quarantine"]


def test_audit_read_filters_by_time_window(
    api_client: TestClient, session_manager: SessionManager, app: FastAPI
) -> None:
    _act_as(api_client, session_manager)
    seeded = SeededAuditLog()
    now = utcnow()
    seeded.seed("old", occurred_at=now - timedelta(days=10))
    seeded.seed("recent", occurred_at=now - timedelta(days=1))
    app.state.audit_log = seeded

    response = api_client.get(
        READ_URL,
        params={"from": to_rfc3339(now - timedelta(days=5)), "to": to_rfc3339(now)},
    )
    assert response.status_code == 200
    assert [entry["action"] for entry in response.json()["entries"]] == ["recent"]


def test_audit_read_paginates_with_an_opaque_cursor(
    api_client: TestClient, session_manager: SessionManager, app: FastAPI
) -> None:
    _act_as(api_client, session_manager)
    for index in range(3):
        _seed_entry(app.state.audit_log, f"action-{index}")

    first = api_client.get(READ_URL, params={"limit": 2}).json()
    assert [entry["action"] for entry in first["entries"]] == ["action-2", "action-1"]
    assert first["nextCursor"] is not None

    second = api_client.get(READ_URL, params={"limit": 2, "cursor": first["nextCursor"]}).json()
    assert [entry["action"] for entry in second["entries"]] == ["action-0"]
    assert second["nextCursor"] is None


def test_audit_read_does_not_write_to_the_log(
    api_client: TestClient, session_manager: SessionManager, app: FastAPI
) -> None:
    _act_as(api_client, session_manager)
    _seed_entry(app.state.audit_log, "provider.create", actor_id="op-1")
    before = app.state.audit_log.entries()

    assert api_client.get(READ_URL).status_code == 200

    after = app.state.audit_log.entries()
    assert len(after) == len(before)
    assert [entry.entry_hash for entry in after] == [entry.entry_hash for entry in before]
    assert app.state.audit_log.verify() is True


def test_audit_read_is_rate_limited(
    settings: Settings, session_manager: SessionManager, db_session_factory: sessionmaker
) -> None:
    application = FastAPI()
    application.state.settings = settings
    application.state.session_factory = db_session_factory
    application.state.session_manager = session_manager
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    register_exception_handlers(application)
    application.include_router(audit_router, prefix="/v1")

    with TestClient(application) as client:
        _act_as(client, session_manager)
        assert client.get(READ_URL).status_code == 200
        limited = client.get(READ_URL)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"


# --------------------------------------------------------------------------- #
# C-042 close finding
# --------------------------------------------------------------------------- #
def _close_url(finding_id: str) -> str:
    return f"/v1/staff/audit/findings/{finding_id}/close"


def test_close_requires_compliance_role_and_mfa(
    api_client: TestClient, session_manager: SessionManager, db_session_factory: sessionmaker
) -> None:
    finding = _open_finding(db_session_factory)
    url = _close_url(finding.id)

    assert api_client.post(url, json={"resolution": "Reconstructed."}).status_code == 401

    _act_as(api_client, session_manager, mfa_verified=False)
    assert api_client.post(url, json={"resolution": "Reconstructed."}).status_code == 403

    _act_as(api_client, session_manager, role=OperatorRole.ADMINISTRATOR)
    assert api_client.post(url, json={"resolution": "Reconstructed."}).status_code == 403


def test_close_unknown_finding_is_404(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    response = api_client.post(_close_url(new_id()), json={"resolution": "Reconstructed."})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_close_records_reviewer_resolution_and_audits(
    api_client: TestClient,
    session_manager: SessionManager,
    app: FastAPI,
    db_session_factory: sessionmaker,
) -> None:
    finding = _open_finding(db_session_factory)
    reviewer = _act_as(api_client, session_manager)

    response = api_client.post(
        _close_url(finding.id), json={"resolution": "Reconstructed from the rail log."}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["findingsId"] == finding.id
    assert body["status"] == "closed"
    assert body["closedAt"].endswith("Z")

    with db_session_factory() as session:
        stored = session.get(ComplianceFinding, finding.id)
        assert stored.status == "closed"
        assert stored.closed_by == reviewer
        assert stored.resolution == "Reconstructed from the rail log."
        assert stored.closed_at is not None

    entries = app.state.audit_log.entries()
    assert entries[-1].action == "audit.finding_closed"
    assert entries[-1].actor_id == reviewer
    assert entries[-1].target == finding.id


def test_close_is_a_conflict_once_closed(
    api_client: TestClient, session_manager: SessionManager, db_session_factory: sessionmaker
) -> None:
    finding = _open_finding(db_session_factory)
    _act_as(api_client, session_manager)

    assert api_client.post(_close_url(finding.id), json={"resolution": "Done."}).status_code == 200
    second = api_client.post(_close_url(finding.id), json={"resolution": "Again."})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_close_rejects_an_empty_resolution(
    api_client: TestClient, session_manager: SessionManager, db_session_factory: sessionmaker
) -> None:
    finding = _open_finding(db_session_factory)
    _act_as(api_client, session_manager)
    response = api_client.post(_close_url(finding.id), json={"resolution": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


# --------------------------------------------------------------------------- #
# C-043 gated export
# --------------------------------------------------------------------------- #
def test_export_requires_compliance_role_and_mfa(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    window = {"from": "2026-09-01T00:00:00Z", "to": "2026-09-10T00:00:00Z", "format": "csv"}

    assert api_client.post("/v1/staff/audit/export", json=window).status_code == 401

    _act_as(api_client, session_manager, mfa_verified=False)
    assert api_client.post("/v1/staff/audit/export", json=window).status_code == 403

    _act_as(api_client, session_manager, role=OperatorRole.ADMINISTRATOR)
    assert api_client.post("/v1/staff/audit/export", json=window).status_code == 403


def test_export_queues_a_job_and_audits_it(
    api_client: TestClient,
    session_manager: SessionManager,
    app: FastAPI,
    db_session_factory: sessionmaker,
) -> None:
    requester = _act_as(api_client, session_manager)
    response = api_client.post(
        "/v1/staff/audit/export",
        json={"from": "2026-09-01T00:00:00Z", "to": "2026-09-10T00:00:00Z", "format": "json"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["exportId"]

    with db_session_factory() as session:
        export = session.get(AuditExport, body["exportId"])
        assert export.requested_by == requester
        assert export.format == "json"
        assert export.status == "queued"
        assert export.range_from < export.range_to

    entries = app.state.audit_log.entries()
    assert entries[-1].action == "audit.export_requested"
    assert entries[-1].actor_id == requester
    assert entries[-1].target == body["exportId"]


def test_export_rejects_a_window_over_the_limit(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    response = api_client.post(
        "/v1/staff/audit/export",
        json={"from": "2026-01-01T00:00:00Z", "to": "2026-06-01T00:00:00Z", "format": "csv"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_export_accepts_a_window_at_the_limit(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    response = api_client.post(
        "/v1/staff/audit/export",
        json={"from": "2026-06-01T00:00:00Z", "to": "2026-08-30T00:00:00Z", "format": "csv"},
    )
    assert response.status_code == 202


def test_export_rejects_an_unknown_format(
    api_client: TestClient, session_manager: SessionManager
) -> None:
    _act_as(api_client, session_manager)
    response = api_client.post(
        "/v1/staff/audit/export",
        json={"from": "2026-09-01T00:00:00Z", "to": "2026-09-10T00:00:00Z", "format": "pdf"},
    )
    assert response.status_code == 422
