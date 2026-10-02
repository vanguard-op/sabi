import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sabi_payments.db.audit import PaymentAuditLog
from sabi_payments.db.base import Base
from sabi_payments.db.models import PaymentAuditRecord


@pytest.fixture
def audit_log() -> PaymentAuditLog:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return PaymentAuditLog(sessionmaker(bind=engine, expire_on_commit=False))


def test_append_builds_a_verifiable_chain(audit_log: PaymentAuditLog) -> None:
    audit_log.append("payment.initiated", actor_id="user-1", target="pay-1")
    audit_log.append("payment.authorized", actor_id="user-1", target="pay-1")
    assert audit_log.verify() is True


def test_tampered_row_breaks_verification(audit_log: PaymentAuditLog) -> None:
    audit_log.append("payment.succeeded", actor_id="system", target="pay-1")
    audit_log.append("payment.refunded", actor_id="system", target="pay-1")

    with audit_log._session_factory() as session:  # noqa: SLF001 (test seam)
        row = session.execute(
            select(PaymentAuditRecord).order_by(PaymentAuditRecord.sequence.asc()).limit(1)
        ).scalar_one()
        row.action = "payment.tampered"
        session.commit()

    assert audit_log.verify() is False
