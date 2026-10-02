from app.core.audit import (
    GENESIS_HASH,
    InMemoryAuditLog,
    build_entry,
    verify_chain,
)


def test_append_builds_a_linked_chain() -> None:
    log = InMemoryAuditLog()
    first = log.append("auth.login", actor_id="user-1")
    second = log.append("provider.review", actor_id="op-1", actor_role="provider_review_analyst")

    assert first.sequence == 1
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.entry_hash
    assert second.sequence == 2
    assert log.verify() is True


def test_tampering_with_a_reason_breaks_the_chain() -> None:
    log = InMemoryAuditLog()
    log.append("auth.login", actor_id="user-1")
    log.append("capability.approve", actor_id="op-1", reason="looks good")

    tampered = log.entries()
    tampered[1].reason = "approved without review"
    assert verify_chain(tampered) is False


def test_removing_an_entry_breaks_the_chain() -> None:
    log = InMemoryAuditLog()
    log.append("a")
    log.append("b")
    log.append("c")

    remaining = log.entries()
    del remaining[1]
    assert verify_chain(remaining) is False


def test_entry_hash_is_stable_for_the_same_material() -> None:
    entry = build_entry(sequence=1, prev_hash=GENESIS_HASH, action="auth.login")
    assert entry.compute_hash() == entry.entry_hash
