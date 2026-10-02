"""Server-side sessions over a signed cookie.

The cookie is HttpOnly, Secure outside development, and SameSite-scoped; the
session itself lives server-side so it can be revoked and so idle and absolute
timeouts are enforced (NFR-026). Channel sessions are short and time-bound
separately (NFR-006).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import Settings
from app.core.ids import new_id
from app.core.time import utcnow

_SAVED_SALT = "sabi.session.v1"


class SessionKind(StrEnum):
    USER = "user"
    OPERATOR = "operator"
    CHANNEL = "channel"


@dataclass(slots=True)
class SessionData:
    id: str
    user_id: str
    kind: SessionKind
    role: str | None
    mfa_verified: bool
    channel: str | None
    issued_at: datetime
    last_seen_at: datetime
    absolute_expires_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> str:
        data = asdict(self)
        data["kind"] = self.kind.value
        for key in ("issued_at", "last_seen_at", "absolute_expires_at"):
            data[key] = data[key].isoformat()
        return json.dumps(data, separators=(",", ":"))

    @classmethod
    def from_payload(cls, payload: str) -> SessionData:
        data = json.loads(payload)
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            kind=SessionKind(data["kind"]),
            role=data.get("role"),
            mfa_verified=bool(data.get("mfa_verified")),
            channel=data.get("channel"),
            issued_at=datetime.fromisoformat(data["issued_at"]),
            last_seen_at=datetime.fromisoformat(data["last_seen_at"]),
            absolute_expires_at=datetime.fromisoformat(data["absolute_expires_at"]),
            metadata=data.get("metadata") or {},
        )


class SessionStore(Protocol):
    def get(self, session_id: str) -> SessionData | None: ...

    def save(self, session: SessionData, ttl_seconds: int) -> None: ...

    def delete(self, session_id: str) -> None: ...

    def delete_for_user(self, user_id: str) -> None: ...


class InMemorySessionStore:
    """Process-local store for development and tests. Not for production."""

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock
        self._sessions: dict[str, tuple[SessionData, datetime]] = {}
        self._by_user: dict[str, set[str]] = {}

    def get(self, session_id: str) -> SessionData | None:
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        session, expires_at = entry
        if expires_at <= self._clock():
            self.delete(session_id)
            return None
        return session

    def save(self, session: SessionData, ttl_seconds: int) -> None:
        expires_at = self._clock() + timedelta(seconds=ttl_seconds)
        self._sessions[session.id] = (session, expires_at)
        self._by_user.setdefault(session.user_id, set()).add(session.id)

    def delete(self, session_id: str) -> None:
        entry = self._sessions.pop(session_id, None)
        if entry is not None:
            self._by_user.get(entry[0].user_id, set()).discard(session_id)

    def delete_for_user(self, user_id: str) -> None:
        for session_id in list(self._by_user.get(user_id, set())):
            self.delete(session_id)


class RedisSessionStore:
    """Redis-backed store. Sessions are cached with a TTL (architecture.md)."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = "sabi:session:"

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def get(self, session_id: str) -> SessionData | None:
        payload = self._client.get(self._key(session_id))
        if payload is None:
            return None
        return SessionData.from_payload(payload)

    def save(self, session: SessionData, ttl_seconds: int) -> None:
        self._client.set(self._key(session.id), session.to_payload(), ex=max(ttl_seconds, 1))
        self._client.sadd(f"sabi:user-sessions:{session.user_id}", session.id)

    def delete(self, session_id: str) -> None:
        session = self.get(session_id)
        self._client.delete(self._key(session_id))
        if session is not None:
            self._client.srem(f"sabi:user-sessions:{session.user_id}", session_id)

    def delete_for_user(self, user_id: str) -> None:
        key = f"sabi:user-sessions:{user_id}"
        for session_id in self._client.smembers(key):
            self._client.delete(self._key(session_id))
        self._client.delete(key)


class SessionManager:
    def __init__(self, settings: Settings, store: SessionStore) -> None:
        self.settings = settings
        self.store = store
        self._serializer = URLSafeTimedSerializer(
            settings.session_secret.get_secret_value(), salt=_SAVED_SALT
        )

    def issue(
        self,
        *,
        user_id: str,
        kind: SessionKind = SessionKind.USER,
        role: str | None = None,
        mfa_verified: bool = False,
        channel: str | None = None,
        ttl_seconds: int | None = None,
    ) -> tuple[str, SessionData]:
        now = utcnow()
        absolute_ttl = ttl_seconds or self.settings.session_absolute_timeout_seconds
        session = SessionData(
            id=new_id(),
            user_id=user_id,
            kind=kind,
            role=role,
            mfa_verified=mfa_verified,
            channel=channel,
            issued_at=now,
            last_seen_at=now,
            absolute_expires_at=now + timedelta(seconds=absolute_ttl),
        )
        self.store.save(session, absolute_ttl)
        token = self._serializer.dumps({"sid": session.id})
        return token, session

    def read(self, token: str) -> SessionData | None:
        if not token:
            return None
        try:
            data = self._serializer.loads(
                token, max_age=self.settings.session_absolute_timeout_seconds
            )
        except (BadSignature, SignatureExpired):
            return None
        session = self.store.get(data["sid"])
        if session is None:
            return None
        now = utcnow()
        if session.absolute_expires_at <= now:
            self.store.delete(session.id)
            return None
        if (now - session.last_seen_at).total_seconds() > self._idle_timeout(session):
            self.store.delete(session.id)
            return None
        self._touch(session, now)
        return session

    def revoke(self, session_id: str) -> None:
        self.store.delete(session_id)

    def _idle_timeout(self, session: SessionData) -> int:
        if session.kind is SessionKind.CHANNEL:
            return self.settings.channel_session_timeout_seconds
        return self.settings.session_idle_timeout_seconds

    def _touch(self, session: SessionData, now: datetime) -> None:
        session.last_seen_at = now
        remaining = int((session.absolute_expires_at - now).total_seconds())
        if remaining <= 0:
            self.store.delete(session.id)
            return
        self.store.save(session, remaining)

    def set_cookie(self, response: Response, token: str, *, max_age: int | None = None) -> None:
        response.set_cookie(
            key=self.settings.session_cookie_name,
            value=token,
            max_age=max_age or self.settings.session_absolute_timeout_seconds,
            httponly=True,
            secure=self.settings.secure_cookies,
            samesite=self.settings.session_cookie_samesite,
            path="/",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=self.settings.session_cookie_name,
            httponly=True,
            secure=self.settings.secure_cookies,
            samesite=self.settings.session_cookie_samesite,
            path="/",
        )
