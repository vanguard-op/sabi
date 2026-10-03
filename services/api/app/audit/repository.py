"""Primary-store access for the compliance review workflow (C-041-C-043).

Only the review entities defined in ``app.audit.models`` are read and written
here. The audit timeline itself is never touched: reads of the append-only log
go through the ``AuditLog`` protocol, and this module offers no update or delete
of a log row (operations-console.md, "Privileged-action audit view").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.models import AuditExport, ComplianceFinding
from app.core.ids import new_id


def get_finding(db: Session, findings_id: str) -> ComplianceFinding | None:
    return db.get(ComplianceFinding, findings_id)


def create_export(
    db: Session,
    *,
    requested_by: str,
    range_from: datetime,
    range_to: datetime,
    export_format: str,
) -> AuditExport:
    export = AuditExport(
        id=new_id(),
        requested_by=requested_by,
        range_from=range_from,
        range_to=range_to,
        format=export_format,
        status="queued",
    )
    db.add(export)
    db.flush()
    return export


__all__ = ["create_export", "get_finding"]
