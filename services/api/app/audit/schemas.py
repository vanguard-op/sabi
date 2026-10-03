"""Wire models for the privileged-action audit view (C-041-C-043).

Field names are camelCase on the wire (DELIVERY.md, conventions). Request models
validate shape only; the cross-record rules (finding state, export range) live in
``app.audit.service`` so they return the contract's error envelope. Timestamps
render as RFC 3339 UTC.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.audit import AuditEntry
from app.core.time import to_rfc3339

# The audit view is read-only over the append-only log; nothing in this module
# accepts a write to ``audit_log`` (operations-console.md).

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# An extract over a wider window is refused rather than queued: a bulk export is
# itself a high-risk action, and bounding the window keeps one request from
# pulling the whole retained history (operations.md, "audit-log review").
MAX_EXPORT_RANGE_DAYS = 90


class AuditEntryOut(BaseModel):
    """One privileged action in the timeline (C-041)."""

    model_config = ConfigDict(populate_by_name=True)

    audit_id: str = Field(alias="auditId")
    actor: str = Field(alias="actor")
    role: str = Field(alias="role")
    target: str = Field(alias="target")
    action: str
    reason: str | None
    occurred_at: str = Field(alias="occurredAt")


class AuditListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    entries: list[AuditEntryOut]
    next_cursor: str | None = Field(alias="nextCursor")


class CloseFindingRequest(BaseModel):
    """C-042 close: the resolution the reviewer records."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    resolution: str = Field(min_length=1, max_length=2000)


class CloseFindingResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    findings_id: str = Field(alias="findingsId")
    status: str
    closed_at: str = Field(alias="closedAt")


class ExportRequest(BaseModel):
    """C-043 export: the requested window and format.

    ``from`` is a Python keyword, so the field binds to the wire name by alias.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    range_from: str = Field(alias="from", min_length=1)
    range_to: str = Field(alias="to", min_length=1)
    format: str = Field(min_length=1)


class ExportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    export_id: str = Field(alias="exportId")
    status: str


def audit_entry(entry: AuditEntry) -> AuditEntryOut:
    """Map a log entry to the wire. A missing actor renders as empty, not null.

    The contract's ``actor``/``role``/``target`` are strings, not nullable, so a
    system action with no actor reads as an empty string rather than breaking
    the shape the console expects.
    """
    return AuditEntryOut(
        audit_id=entry.id,
        actor=entry.actor_id or "",
        role=entry.actor_role or "",
        target=entry.target or "",
        action=entry.action,
        reason=entry.reason,
        occurred_at=to_rfc3339(entry.occurred_at),
    )


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_EXPORT_RANGE_DAYS",
    "MAX_LIMIT",
    "AuditEntryOut",
    "AuditListResponse",
    "CloseFindingRequest",
    "CloseFindingResponse",
    "ExportRequest",
    "ExportResponse",
    "audit_entry",
]
