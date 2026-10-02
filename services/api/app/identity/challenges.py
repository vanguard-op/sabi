"""Short-lived, single-use WebAuthn challenge store.

The options endpoint mints a challenge and the matching verify endpoint consumes
it, so a replayed or stale challenge is rejected rather than re-verified
(C-001..C-004). State lives server-side and is keyed by an opaque challenge id;
it holds no secret beyond the ceremony's random challenge and the pending
account's display preferences.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from fastapi import Request

from app.core.time import utcnow

# How long a client has to return a ceremony response. Deliberately short: the
# WebAuthn timeout hint is 60s; a stale challenge must not linger.
CHALLENGE_TTL_SECONDS = 300


class ChallengeKind(StrEnum):
    REGISTRATION = "registration"
    AUTHENTICATION = "authentication"


@dataclass(slots=True)
class Challenge:
    """One in-flight ceremony: a random challenge, single-use and time-boxed.

    The verification step already carries the account preferences, so the store
    holds only what the ceremony needs to complete.
    """

    id: str
    kind: ChallengeKind
    challenge: bytes
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or utcnow())


class ChallengeStore(Protocol):
    def put(self, challenge: Challenge) -> None: ...

    def consume(self, challenge_id: str) -> Challenge | None:
        """Return and remove a challenge; None when unknown or expired."""


class InMemoryChallengeStore:
    """Process-local store for development and single-process deployments.

    A production deployment with more than one worker pins a shared store on
    ``app.state.webauthn_challenges`` before serving traffic.
    """

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock
        self._items: dict[str, Challenge] = {}
        self._lock = threading.Lock()

    def put(self, challenge: Challenge) -> None:
        with self._lock:
            self._items[challenge.id] = challenge

    def consume(self, challenge_id: str) -> Challenge | None:
        with self._lock:
            challenge = self._items.pop(challenge_id, None)
        if challenge is None or challenge.is_expired(self._clock()):
            return None
        return challenge

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def get_challenge_store(request: Request) -> ChallengeStore:
    store = getattr(request.app.state, "webauthn_challenges", None)
    if store is None:
        store = InMemoryChallengeStore()
        request.app.state.webauthn_challenges = store
    return store
