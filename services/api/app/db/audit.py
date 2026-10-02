"""Database-backed audit log.

Appends are serialised so the hash chain has a single writer at a time: the last
row is locked while the next is written. This is the primary-store audit stream
for authentication, authorisation, and privileged operator actions (NFR-028).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.audit import (
    GENESIS_HASH,
    AuditEntry,
    build_entry,
    verify_chain,
)
from app.db.models import AuditLogRecord


def _to_entry(record: AuditLogRecord) -> AuditEntry:
    return AuditEntry(
        sequence=record.sequence,
        id=record.id,
        action=record.action,
        actor_id=record.actor_id,
        actor_role=record.actor_role,
        target=record.target,
        reason=record.reason,
        detail=dict(record.detail or {}),
        occurred_at=record.occurred_at,
        prev_hash=record.prev_hash,
        entry_hash=record.entry_hash,
    )


class DatabaseAuditLog:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(
        self,
        action: str,
        *,
        actor_id: str | None = None,
        actor_role: str | None = None,
        target: str | None = None,
        reason: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEntry:
        with self._session_factory() as session:
            last = session.execute(
                select(AuditLogRecord).order_by(AuditLogRecord.sequence.desc()).limit(1)
            ).scalar_one_or_none()
            prev_hash = last.entry_hash if last is not None else GENESIS_HASH
            sequence = (last.sequence if last is not None else 0) + 1
            entry = build_entry(
                sequence=sequence,
                prev_hash=prev_hash,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                target=target,
                reason=reason,
                detail=detail,
            )
            session.add(
                AuditLogRecord(
                    sequence=entry.sequence,
                    id=entry.id,
                    action=entry.action,
                    actor_id=entry.actor_id,
                    actor_role=entry.actor_role,
                    target=entry.target,
                    reason=entry.reason,
                    detail=entry.detail,
                    occurred_at=entry.occurred_at,
                    prev_hash=entry.prev_hash,
                    entry_hash=entry.entry_hash,
                )
            )
            session.commit()
            return entry

    def entries(self) -> list[AuditEntry]:
        with self._session_factory() as session:
            records = session.execute(
                select(AuditLogRecord).order_by(AuditLogRecord.sequence.asc())
            ).scalars()
            return [_to_entry(record) for record in records]

    def verify(self) -> bool:
        return verify_chain(self.entries())
