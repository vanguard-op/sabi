"""Compliance review rules over the privileged-action audit view (C-041-C-043).

The router stays thin; this layer holds the filtering, the finding state rule,
and the export window bound, and raises the contract's errors. It reads the
append-only log only through ``AuditLog`` and appends to it for the two
privileged actions the view performs: closing a finding and requesting an
export (operations.md, "Privileged-action and audit-log review").
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.audit import repository
from app.audit.models import AuditExport, ComplianceFinding
from app.audit.schemas import (
    DEFAULT_LIMIT,
    MAX_EXPORT_RANGE_DAYS,
    MAX_LIMIT,
    AuditEntryOut,
    AuditListResponse,
    CloseFindingResponse,
    ExportResponse,
    audit_entry,
)
from app.core.audit import AuditEntry, AuditLog
from app.core.errors import APIError, ErrorCode
from app.core.sessions import SessionData
from app.core.time import utcnow


def _bad_request(message: str) -> APIError:
    return APIError(422, ErrorCode.VALIDATION_FAILED, message)


def _finding_not_found() -> APIError:
    return APIError(404, ErrorCode.NOT_FOUND, "That finding does not exist.")


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an RFC 3339 bound, or None when absent.

    A bound is a filter, not a resource: a value the console cannot parse is
    ignored rather than failing the read, so the contract's 200 path is always
    reachable (C-041 lists no 422 for the read).
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _encode_cursor(entry: AuditEntry) -> str:
    return base64.urlsafe_b64encode(str(entry.sequence).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str) -> int | None:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None


def _matches(
    entry: AuditEntry,
    *,
    actor: str | None,
    role: str | None,
    target: str | None,
    action: str | None,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
) -> bool:
    if actor is not None and entry.actor_id != actor:
        return False
    if role is not None and entry.actor_role != role:
        return False
    if target is not None and entry.target != target:
        return False
    if action is not None and entry.action != action:
        return False
    if occurred_from is not None and entry.occurred_at < occurred_from:
        return False
    if occurred_to is not None and entry.occurred_at > occurred_to:
        return False
    return True


def read_audit(
    audit: AuditLog,
    *,
    actor: str | None = None,
    role: str | None = None,
    target: str | None = None,
    action: str | None = None,
    range_from: str | None = None,
    range_to: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> AuditListResponse:
    """Newest-first page of the timeline, filtered and keyset-paginated.

    The log's ``sequence`` is monotonic, so it is the keyset: the next page
    holds entries below the cursor's sequence. The cursor is opaque to the
    console. An unparseable cursor starts from the newest entry rather than
    failing, since C-041 lists no error for a malformed cursor.
    """
    occurred_from = _parse_timestamp(range_from)
    occurred_to = _parse_timestamp(range_to)
    bounded = max(1, min(limit, MAX_LIMIT))

    entries = [
        entry
        for entry in audit.entries()
        if _matches(
            entry,
            actor=actor,
            role=role,
            target=target,
            action=action,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
    ]
    entries.sort(key=lambda entry: entry.sequence, reverse=True)

    after = _decode_cursor(cursor) if cursor else None
    if after is not None:
        entries = [entry for entry in entries if entry.sequence < after]

    page = entries[:bounded]
    next_cursor = _encode_cursor(page[-1]) if len(entries) > bounded and page else None

    rendered: list[AuditEntryOut] = [audit_entry(entry) for entry in page]
    return AuditListResponse(entries=rendered, next_cursor=next_cursor)


def close_finding(
    db: Session,
    audit: AuditLog,
    *,
    actor: SessionData,
    findings_id: str,
    resolution: str,
) -> CloseFindingResponse:
    """Close an open finding once and record the reviewer.

    A second close is a conflict, not a no-op: the resolution the first reviewer
    recorded is the record of the review (operations.md). The close is itself a
    privileged action and is appended to the log; the resolution text may name a
    person, so it stays in the review row and is not copied into the log.
    """
    finding: ComplianceFinding | None = repository.get_finding(db, findings_id)
    if finding is None:
        raise _finding_not_found()
    if finding.status != "open":
        raise APIError(409, ErrorCode.CONFLICT, "That finding is already closed.")

    now = utcnow()
    finding.status = "closed"
    finding.closed_by = actor.user_id
    finding.resolution = resolution
    finding.closed_at = now
    db.flush()

    audit.append(
        "audit.finding_closed",
        actor_id=actor.user_id,
        actor_role=actor.role,
        target=finding.id,
        detail={"blockedRole": finding.blocked_role},
    )
    return CloseFindingResponse(
        findings_id=finding.id,
        status=finding.status,
        closed_at=now.isoformat().replace("+00:00", "Z"),
    )


def request_export(
    db: Session,
    audit: AuditLog,
    *,
    actor: SessionData,
    range_from: str,
    range_to: str,
    export_format: str,
) -> ExportResponse:
    """Queue an audit extract, bounded so one request cannot pull all history.

    A bulk export is itself a high-risk privileged action and is logged
    (operations-console.md; operations.md, alerts on bulk data export). The
    extract is produced by the export worker, so the job row holds only the
    window and format, never the extracted rows.
    """
    start = _parse_required_timestamp("from", range_from)
    end = _parse_required_timestamp("to", range_to)
    if start > end:
        raise _bad_request("The export window runs backwards.")
    if end - start > timedelta(days=MAX_EXPORT_RANGE_DAYS):
        raise _bad_request(f"An export may cover at most {MAX_EXPORT_RANGE_DAYS} days.")

    normalised_format = export_format.strip().lower()
    if normalised_format not in ("csv", "json"):
        raise _bad_request("The export format must be csv or json.")

    export: AuditExport = repository.create_export(
        db,
        requested_by=actor.user_id,
        range_from=start,
        range_to=end,
        export_format=normalised_format,
    )
    audit.append(
        "audit.export_requested",
        actor_id=actor.user_id,
        actor_role=actor.role,
        target=export.id,
        detail={"from": start.isoformat(), "to": end.isoformat(), "format": normalised_format},
    )
    return ExportResponse(export_id=export.id, status=export.status)


def _parse_required_timestamp(field: str, value: str) -> datetime:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise _bad_request(f"The export {field} must be an RFC 3339 timestamp.")
    return parsed
