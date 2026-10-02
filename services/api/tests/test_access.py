import pytest

from app.core.access import OperatorRole, operator_has_access, require_operator, require_user
from app.core.errors import APIError
from app.core.ids import new_id
from app.core.sessions import SessionData, SessionKind
from app.core.time import utcnow


def make_session(
    *,
    kind: SessionKind = SessionKind.OPERATOR,
    role: str | None = OperatorRole.PROVIDER_REVIEW_ANALYST,
    mfa_verified: bool = True,
) -> SessionData:
    now = utcnow()
    return SessionData(
        id=new_id(),
        user_id=new_id(),
        kind=kind,
        role=role,
        mfa_verified=mfa_verified,
        channel=None,
        issued_at=now,
        last_seen_at=now,
        absolute_expires_at=now,
    )


def test_require_user_rejects_anonymous() -> None:
    with pytest.raises(APIError) as error:
        require_user(None)
    assert error.value.status_code == 401


def test_require_user_accepts_any_session() -> None:
    session = make_session(kind=SessionKind.USER, role=None, mfa_verified=False)
    assert require_user(session) is session


def test_operator_needs_operator_kind() -> None:
    session = make_session(kind=SessionKind.USER, role=None, mfa_verified=False)
    with pytest.raises(APIError) as error:
        require_operator(session, [OperatorRole.PROVIDER_REVIEW_ANALYST])
    assert error.value.status_code == 403


def test_operator_needs_mfa() -> None:
    session = make_session(mfa_verified=False)
    assert operator_has_access(session, [OperatorRole.PROVIDER_REVIEW_ANALYST]) is False
    with pytest.raises(APIError) as error:
        require_operator(session, [OperatorRole.PROVIDER_REVIEW_ANALYST])
    assert error.value.status_code == 403


def test_operator_needs_the_assigned_role() -> None:
    session = make_session(role=OperatorRole.SUPPORT_OPERATIONS_AGENT)
    with pytest.raises(APIError):
        require_operator(session, [OperatorRole.PROVIDER_REVIEW_ANALYST])
    assert require_operator(session, [OperatorRole.SUPPORT_OPERATIONS_AGENT]) is session


def test_require_operator_rejects_anonymous_with_401() -> None:
    with pytest.raises(APIError) as error:
        require_operator(None, [OperatorRole.PROVIDER_REVIEW_ANALYST])
    assert error.value.status_code == 401
