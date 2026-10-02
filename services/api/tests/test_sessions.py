from datetime import timedelta

from helpers import make_settings
from starlette.responses import Response

from app.core.ids import is_uuid7
from app.core.security import mask_identifier, new_nonce
from app.core.sessions import (
    InMemorySessionStore,
    SessionKind,
    SessionManager,
)
from app.core.time import utcnow


def test_issue_and_read_roundtrip() -> None:
    manager = SessionManager(make_settings(), InMemorySessionStore())
    token, session = manager.issue(user_id="user-1")
    assert is_uuid7(session.id)
    loaded = manager.read(token)
    assert loaded is not None
    assert loaded.user_id == "user-1"
    assert loaded.kind is SessionKind.USER


def test_garbage_token_is_rejected() -> None:
    manager = SessionManager(make_settings(), InMemorySessionStore())
    assert manager.read("not-a-token") is None
    assert manager.read("") is None


def test_revoked_session_is_rejected() -> None:
    manager = SessionManager(make_settings(), InMemorySessionStore())
    token, session = manager.issue(user_id="user-1")
    manager.revoke(session.id)
    assert manager.read(token) is None


def test_idle_timeout_expires_a_user_session() -> None:
    settings = make_settings(session_idle_timeout_seconds=10)
    store = InMemorySessionStore()
    manager = SessionManager(settings, store)
    token, session = manager.issue(user_id="user-1")
    session.last_seen_at = utcnow() - timedelta(seconds=11)
    store.save(session, settings.session_absolute_timeout_seconds)
    assert manager.read(token) is None


def test_channel_session_has_a_shorter_idle_timeout() -> None:
    settings = make_settings(session_idle_timeout_seconds=3600, channel_session_timeout_seconds=120)
    store = InMemorySessionStore()
    manager = SessionManager(settings, store)
    user_token, user_session = manager.issue(user_id="user-1")
    channel_token, channel_session = manager.issue(
        user_id="user-1", kind=SessionKind.CHANNEL, channel="ussd"
    )
    stale = utcnow() - timedelta(seconds=121)
    user_session.last_seen_at = stale
    channel_session.last_seen_at = stale
    store.save(user_session, 3600)
    store.save(channel_session, 3600)

    assert manager.read(user_token) is not None
    assert manager.read(channel_token) is None


def test_absolute_timeout_expires_even_when_active() -> None:
    settings = make_settings()
    store = InMemorySessionStore()
    manager = SessionManager(settings, store)
    token, session = manager.issue(user_id="user-1")
    session.absolute_expires_at = utcnow() - timedelta(seconds=1)
    store.save(session, settings.session_absolute_timeout_seconds)
    assert manager.read(token) is None


def test_development_cookie_flags() -> None:
    manager = SessionManager(make_settings(), InMemorySessionStore())
    response = Response()
    manager.set_cookie(response, "token-value")
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Secure" not in header  # local development over plain HTTP


def test_production_cookie_is_secure() -> None:
    settings = make_settings(
        environment="production",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
    )
    manager = SessionManager(settings, InMemorySessionStore())
    response = Response()
    manager.set_cookie(response, "token-value")
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "Secure" in header


def test_masked_identifier_helper_and_nonce() -> None:
    assert mask_identifier("0123456789") == "******6789"
    assert len(new_nonce()) >= 20
