"""Challenge store behaviour: single-use and time-boxed (C-001..C-004)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.identity.challenges import Challenge, ChallengeKind, InMemoryChallengeStore


def _challenge(challenge_id: str, *, expires_at: datetime) -> Challenge:
    return Challenge(
        id=challenge_id,
        kind=ChallengeKind.REGISTRATION,
        challenge=b"random",
        expires_at=expires_at,
    )


def test_challenge_is_single_use() -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = InMemoryChallengeStore(clock=lambda: now[0])
    challenge = _challenge("c1", expires_at=now[0] + timedelta(seconds=60))
    store.put(challenge)

    assert store.consume("c1") is challenge
    assert store.consume("c1") is None


def test_expired_challenge_is_rejected_and_dropped() -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = InMemoryChallengeStore(clock=lambda: now[0])
    store.put(_challenge("c2", expires_at=now[0] + timedelta(seconds=5)))

    now[0] += timedelta(seconds=6)

    assert store.consume("c2") is None
    assert store.consume("c2") is None


def test_unknown_challenge_is_none() -> None:
    store = InMemoryChallengeStore()
    assert store.consume("missing") is None
