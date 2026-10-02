"""Tamper-evident audit log.

Authentication, authorisation, and privileged actions are appended to a hash
chain: each entry commits to the previous entry's hash, so altering or removing
an entry breaks every later hash (NFR-028). The log is append-only; nothing here
offers an update or delete.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol

from app.core.ids import new_id
from app.core.time import to_rfc3339, utcnow

GENESIS_HASH = "0" * 64


@dataclass(slots=True)
class AuditEntry:
    sequence: int
    id: str
    action: str
    actor_id: str | None
    actor_role: str | None
    target: str | None
    reason: str | None
    detail: dict[str, Any]
    occurred_at: datetime
    prev_hash: str
    entry_hash: str = ""

    def material(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("entry_hash")
        data["occurred_at"] = to_rfc3339(self.occurred_at)
        return data

    def compute_hash(self) -> str:
        canonical = json.dumps(self.material(), sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()


def build_entry(
    *,
    sequence: int,
    prev_hash: str,
    action: str,
    actor_id: str | None = None,
    actor_role: str | None = None,
    target: str | None = None,
    reason: str | None = None,
    detail: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        sequence=sequence,
        id=new_id(),
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        target=target,
        reason=reason,
        detail=detail or {},
        occurred_at=occurred_at or utcnow(),
        prev_hash=prev_hash,
    )
    entry.entry_hash = entry.compute_hash()
    return entry


def verify_chain(entries: list[AuditEntry]) -> bool:
    """Recompute the chain. Any edit, reorder, or removal returns False."""
    prev_hash = GENESIS_HASH
    for index, entry in enumerate(entries, start=1):
        if entry.sequence != index or entry.prev_hash != prev_hash:
            return False
        if entry.compute_hash() != entry.entry_hash:
            return False
        prev_hash = entry.entry_hash
    return True


class AuditLog(Protocol):
    def append(
        self,
        action: str,
        *,
        actor_id: str | None = None,
        actor_role: str | None = None,
        target: str | None = None,
        reason: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEntry: ...

    def entries(self) -> list[AuditEntry]: ...

    def verify(self) -> bool: ...


class InMemoryAuditLog:
    """Process-local audit log for development and tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[AuditEntry] = []

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
        with self._lock:
            prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
            entry = build_entry(
                sequence=len(self._entries) + 1,
                prev_hash=prev_hash,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                target=target,
                reason=reason,
                detail=detail,
            )
            self._entries.append(entry)
            return entry

    def entries(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries)

    def verify(self) -> bool:
        return verify_chain(self.entries())
