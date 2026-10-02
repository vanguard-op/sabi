"""Time helpers. Timestamps are RFC 3339 in UTC (DELIVERY.md, conventions)."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_rfc3339(value: datetime) -> str:
    """Render a datetime as an RFC 3339 UTC string with a trailing Z."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
