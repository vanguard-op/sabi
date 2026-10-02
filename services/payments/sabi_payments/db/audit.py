"""Hash-chained audit stream for the payment module.

Append-only: each row commits to its predecessor, so editing or removing a row
breaks the chain. Mirrors the primary-store trail but stays inside the module so
the payment store can be extracted whole.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sabi_payments.core.ids import new_id
from sabi_payments.db.models import PaymentAuditRecord

GENESIS_HASH = "0" * 64


def _material(record: PaymentAuditRecord) -> dict[str, Any]:
    occurred_at = record.occurred_at
    if occurred_at.tzinfo is None:
        # SQLite drops tzinfo; treat stored values as UTC so the hash is stable
        # between the append and a later verification read.
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return {
        "sequence": record.sequence,
        "id": record.id,
        "action": record.action,
        "actor_id": record.actor_id,
        "target": record.target,
        "detail": record.detail or {},
        "occurred_at": occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "prev_hash": record.prev_hash,
    }


def _hash(record: PaymentAuditRecord) -> str:
    canonical = json.dumps(_material(record), sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


class PaymentAuditLog:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(
        self,
        action: str,
        *,
        actor_id: str | None = None,
        target: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> PaymentAuditRecord:
        with self._session_factory() as session:
            last = session.execute(
                select(PaymentAuditRecord).order_by(PaymentAuditRecord.sequence.desc()).limit(1)
            ).scalar_one_or_none()
            record = PaymentAuditRecord(
                sequence=(last.sequence if last else 0) + 1,
                id=new_id(),
                action=action,
                actor_id=actor_id,
                target=target,
                detail=detail or {},
                occurred_at=datetime.now(UTC),
                prev_hash=last.entry_hash if last else GENESIS_HASH,
            )
            record.entry_hash = _hash(record)
            session.add(record)
            session.commit()
            return record

    def verify(self) -> bool:
        with self._session_factory() as session:
            records = list(
                session.execute(
                    select(PaymentAuditRecord).order_by(PaymentAuditRecord.sequence.asc())
                ).scalars()
            )
        prev_hash = GENESIS_HASH
        for index, record in enumerate(records, start=1):
            if record.sequence != index or record.prev_hash != prev_hash:
                return False
            if _hash(record) != record.entry_hash:
                return False
            prev_hash = record.entry_hash
        return True
