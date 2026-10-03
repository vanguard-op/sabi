"""Unit tests for the reconciliation and refund jobs (FEAT-006/007/009).

The payment module is a separate store, so these tests bind in-memory doubles
for the two boundaries the jobs reach across: the reconciliation port
(``app.reconciliation.ports``) for the window of internal payments and external
statements, and the shared payment port (``app.payments_port``) for the
user-scoped payment read and the rail refund. The case table is the real
primary-store entity on an isolated SQLite database, since opening a case once
per condition is the behaviour under test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import InMemoryAuditLog
from app.db.base import Base
from app.db.models import PaymentCase
from app.payments_port import InMemoryPaymentLookup, PaymentView, RefundView
from app.reconciliation import refunds, rules, windows
from app.reconciliation.jobs import run_daily_reconciliation, run_scheduled_jobs
from app.reconciliation.ports import (
    InMemoryPaymentSource,
    InMemoryStatementSource,
    PaymentRecord,
    StatementLine,
)

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
# SQLite hands back naive datetimes for timezone-aware columns, so the case
# fixtures below seed a naive ``opened_at``. The window arithmetic normalises a
# naive value (and a naive clock) to UTC, so the job accepts an aware or a naive
# ``now`` against either kind of ``opened_at``; these tests pin the naive clock
# to exercise that normalisation. Postgres returns aware timestamps and the
# production caller passes utcnow().
NAIVE_NOW = NOW.replace(tzinfo=None)
WINDOW_START = NAIVE_NOW - timedelta(days=1)
WINDOW_END = NAIVE_NOW


class FakeRail(InMemoryPaymentLookup):
    """User-scoped payment reads plus the rail refund, in one double."""

    def __init__(self) -> None:
        super().__init__()
        self.refund_calls: list[tuple[str, str, str, str]] = []
        self.refund_result = RefundView(status="reversed", refund_reference="rail-refund-1")

    def add_payment(
        self,
        payment_id: str,
        *,
        user_id: str = "user-1",
        status: str = "succeeded",
        reference: str | None = "rail-1",
    ) -> PaymentView:
        record = PaymentView(
            payment_id=payment_id,
            user_id=user_id,
            service_id="svc-1",
            reference=reference,
            payee="Onitsha South LGA",
            amount=50_000,
            currency="NGN",
            status=status,
            channel="app",
            created_at=NOW,
            updated_at=NOW,
        )
        self.add(record)
        return record

    def refund(
        self, *, user_id: str, payment_id: str, reason: str, idempotency_key: str
    ) -> RefundView:
        self.refund_calls.append((user_id, payment_id, reason, idempotency_key))
        return self.refund_result


class RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def notify(self, *, user_id: str, template: str, detail: str | None = None) -> None:
        self.calls.append((user_id, template, detail))


@pytest.fixture
def db_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_factory: sessionmaker[Session]) -> Iterator[Session]:
    with db_factory() as session:
        yield session


@pytest.fixture
def rail() -> FakeRail:
    return FakeRail()


@pytest.fixture
def audit() -> InMemoryAuditLog:
    return InMemoryAuditLog()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


def _payment(
    payment_id: str = "pay-1",
    *,
    reference: str | None = "rail-1",
    amount: int = 50_000,
    currency: str = "NGN",
    federal: bool = False,
    destination: str | None = None,
    created_at: datetime | None = NAIVE_NOW - timedelta(hours=1),
) -> PaymentRecord:
    return PaymentRecord(
        payment_id=payment_id,
        user_id="user-1",
        reference=reference,
        amount=amount,
        currency=currency,
        payee="Onitsha South LGA",
        status="succeeded",
        federal=federal,
        destination=destination,
        created_at=created_at,
    )


def _line(
    reference: str,
    *,
    amount: int = 50_000,
    currency: str = "NGN",
    kind: str = "rail",
    deduction: int = 0,
    destination: str | None = None,
    payment_id: str | None = None,
) -> StatementLine:
    return StatementLine(
        reference=reference,
        amount=amount,
        currency=currency,
        kind=kind,
        deduction=deduction,
        destination=destination,
        payment_id=payment_id,
    )


def _cases(db: Session, **filters: str) -> list[PaymentCase]:
    stmt = select(PaymentCase)
    for column, value in filters.items():
        stmt = stmt.where(getattr(PaymentCase, column) == value)
    return list(db.execute(stmt.order_by(PaymentCase.id.asc())).scalars())


# --- rules: pure correlation (FEAT-006, FEAT-009) --------------------------


def test_agreeing_records_match() -> None:
    items, exceptions = rules.correlate([_payment()], [_line("rail-1")])
    assert [item.outcome for item in items] == [rules.MatchOutcome.MATCHED]
    assert exceptions == []


def test_amount_disagreement_is_a_mismatch_and_a_dispute() -> None:
    items, exceptions = rules.correlate([_payment()], [_line("rail-1", amount=49_999)])
    assert items[0].outcome is rules.MatchOutcome.MISMATCHED
    assert len(exceptions) == 1
    assert exceptions[0].case_type is rules.ExceptionType.DISPUTED
    assert exceptions[0].escalate is False


def test_currency_disagreement_is_a_mismatch() -> None:
    items, exceptions = rules.correlate([_payment()], [_line("rail-1", currency="USD")])
    assert items[0].outcome is rules.MatchOutcome.MISMATCHED
    assert exceptions[0].case_type is rules.ExceptionType.DISPUTED


def test_a_debit_with_no_statement_line_is_failed_no_delivery() -> None:
    items, exceptions = rules.correlate([_payment()], [])
    assert items[0].outcome is rules.MatchOutcome.NO_DELIVERY
    assert exceptions[0].case_type is rules.ExceptionType.FAILED_NO_DELIVERY
    assert exceptions[0].payment_id == "pay-1"
    assert exceptions[0].user_id == "user-1"


def test_federal_deduction_escalates_a_dispute() -> None:
    _, exceptions = rules.correlate(
        [_payment(federal=True, destination="treasury-1")],
        [_line("rail-1", deduction=500, destination="treasury-1")],
    )
    assert exceptions[0].case_type is rules.ExceptionType.DISPUTED
    assert exceptions[0].escalate is True


def test_federal_wrong_destination_escalates_a_dispute() -> None:
    _, exceptions = rules.correlate(
        [_payment(federal=True, destination="treasury-1")],
        [_line("rail-1", destination="somewhere-else")],
    )
    assert exceptions[0].escalate is True


def test_federal_collection_to_the_right_account_with_no_deduction_matches() -> None:
    items, exceptions = rules.correlate(
        [_payment(federal=True, destination="treasury-1")],
        [_line("rail-1", destination="treasury-1")],
    )
    assert items[0].outcome is rules.MatchOutcome.MATCHED
    assert exceptions == []


def test_reference_less_payment_matches_by_payment_id() -> None:
    items, exceptions = rules.correlate(
        [_payment(reference=None)],
        [_line("agency-9", payment_id="pay-1")],
    )
    assert items[0].outcome is rules.MatchOutcome.MATCHED
    assert exceptions == []


def test_an_orphan_rail_line_is_receipt_missing_without_an_owner() -> None:
    items, exceptions = rules.correlate([], [_line("rail-orphan", kind="rail")])
    assert items == []
    assert exceptions[0].case_type is rules.ExceptionType.RECEIPT_MISSING
    assert exceptions[0].user_id == ""


def test_an_orphan_agency_line_is_failed_no_delivery() -> None:
    _, exceptions = rules.correlate([], [_line("agency-orphan", kind="agency")])
    assert exceptions[0].case_type is rules.ExceptionType.FAILED_NO_DELIVERY


# --- jobs: daily reconciliation -------------------------------------------


def _run(db, rail, audit, notifier, *, payments=(), statements=(), **kwargs):  # type: ignore[no-untyped-def]
    return run_daily_reconciliation(
        db,
        InMemoryPaymentSource(payments),
        InMemoryStatementSource(statements),
        audit=audit,
        notifier=notifier,
        since=WINDOW_START,
        until=WINDOW_END,
        now=NAIVE_NOW,
        **kwargs,
    )


def test_daily_reconciliation_opens_a_case_for_an_undelivered_debit(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    report = _run(db, rail, audit, notifier, payments=[_payment()])
    assert report.payments_checked == 1
    assert report.matched == 0
    assert report.exception_cases_opened == 1

    cases = _cases(db)
    assert len(cases) == 1
    assert cases[0].type == "failed_no_delivery"
    assert cases[0].status == "open"
    assert notifier.calls[0][0] == "user-1"
    # The run is recorded for operator review.
    assert [entry.action for entry in audit.entries()] == [
        "reconciliation.exception",
        "reconciliation.run",
    ]


def test_a_retried_reconciliation_does_not_multiply_cases(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    _run(db, rail, audit, notifier, payments=[_payment()])
    second = _run(db, rail, audit, notifier, payments=[_payment()])
    assert second.exception_cases_opened == 0
    assert second.exceptions_deferred == 1
    assert len(_cases(db)) == 1


def test_reconciliation_matches_without_opening_a_case(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    report = _run(db, rail, audit, notifier, payments=[_payment()], statements=[_line("rail-1")])
    assert report.matched == 1
    assert report.exception_cases_opened == 0
    assert _cases(db) == []


def test_an_orphan_statement_line_is_audited_not_cased(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    report = _run(db, rail, audit, notifier, statements=[_line("rail-orphan")])
    assert report.exception_cases_opened == 0
    assert _cases(db) == []
    assert notifier.calls == []
    assert audit.entries()[0].action == "reconciliation.exception"
    assert audit.entries()[0].target == "rail-orphan"


def test_detection_with_the_refund_boundary_refunds_and_cases(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    rail.add_payment("pay-1", status="succeeded")
    report = _run(
        db,
        rail,
        audit,
        notifier,
        payments=[_payment()],
        payment_lookup=rail,
        refund_port=rail,
    )
    assert report.refunds_initiated == 1
    # The refund reached the rail once, under the stable reference key.
    assert rail.refund_calls == [
        ("user-1", "pay-1", "The payment was debited without delivery.", "refund:rail-1")
    ]
    types = [case.type for case in _cases(db)]
    assert types == ["failed_no_delivery", "refund"]
    assert "refund_initiated" in [call[1] for call in notifier.calls]


def test_a_federal_mismatch_escalates_on_the_spot(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    _run(
        db,
        rail,
        audit,
        notifier,
        payments=[_payment(federal=True, destination="treasury-1")],
        statements=[_line("rail-1", deduction=100, destination="treasury-1")],
    )
    case = _cases(db)[0]
    assert case.type == "disputed"
    assert case.status == "escalated"
    assert case.assignee_role == "reconciliation_officer"


# --- refunds: planning and execution (FEAT-009) ---------------------------


def test_terminal_refund_state_is_a_blocked_duplicate(db: Session, rail: FakeRail) -> None:
    rail.add_payment("pay-1", status="refunded")
    plans = refunds.plan_refunds(db, rail, user_id="user-1", payment_ids=["pay-1"])
    assert plans[0].decision is refunds.RefundDecision.DUPLICATE


def test_an_open_refund_case_is_a_blocked_duplicate(db: Session, rail: FakeRail) -> None:
    rail.add_payment("pay-1", status="succeeded")
    db.add(
        PaymentCase(
            id="case-1",
            payment_id="pay-1",
            user_id="user-1",
            type="refund",
            status="awaiting_provider",
            assignee_role="support_operations_agent",
            opened_at=NOW,
            updated_at=NOW,
        )
    )
    db.flush()
    plans = refunds.plan_refunds(db, rail, user_id="user-1", payment_ids=["pay-1"])
    assert plans[0].decision is refunds.RefundDecision.DUPLICATE


def test_a_pending_payment_is_not_refundable(db: Session, rail: FakeRail) -> None:
    rail.add_payment("pay-1", status="pending")
    plans = refunds.plan_refunds(db, rail, user_id="user-1", payment_ids=["pay-1"])
    assert plans[0].decision is refunds.RefundDecision.NOT_REFUNDABLE


def test_another_users_payment_is_never_refunded(db: Session, rail: FakeRail) -> None:
    rail.add_payment("pay-1", user_id="user-2", status="succeeded")
    plans = refunds.plan_refunds(db, rail, user_id="user-1", payment_ids=["pay-1"])
    assert plans == []


def test_the_sweep_refunds_once_opens_a_case_and_notifies(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    rail.add_payment("pay-1", status="succeeded")
    outcomes = refunds.run_refund_sweep(
        db,
        rail,
        rail,
        user_id="user-1",
        payment_ids=["pay-1"],
        audit=audit,
        notifier=notifier,
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "reversed"
    assert len(rail.refund_calls) == 1
    assert [case.type for case in _cases(db)] == ["refund"]
    assert audit.entries()[0].action == "refund.initiated"

    # A second sweep sees the open refund case and never asks the rail again.
    outcomes = refunds.run_refund_sweep(
        db,
        rail,
        rail,
        user_id="user-1",
        payment_ids=["pay-1"],
        audit=audit,
        notifier=notifier,
    )
    assert outcomes == []
    assert len(rail.refund_calls) == 1
    assert len(_cases(db)) == 1


def test_an_unsettled_rail_result_leaves_no_tracking_case(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    rail.add_payment("pay-1", status="succeeded")
    rail.refund_result = RefundView(status="pending", refund_reference=None)
    outcomes = refunds.run_refund_sweep(
        db,
        rail,
        rail,
        user_id="user-1",
        payment_ids=["pay-1"],
        audit=audit,
        notifier=notifier,
    )
    assert outcomes == []
    assert _cases(db) == []


def test_settlement_resolves_a_refund_case_the_rail_acknowledged(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    db.add(
        PaymentCase(
            id="case-refund-1",
            payment_id="pay-1",
            user_id="user-1",
            type="refund",
            status="awaiting_provider",
            assignee_role="support_operations_agent",
            opened_at=NOW,
            updated_at=NOW,
        )
    )
    db.flush()
    rail.add_payment("pay-1", status="refunded")

    resolved = refunds.settle_refund_cases(db, rail, audit=audit, notifier=notifier, now=NOW)
    assert resolved == ["case-refund-1"]
    case = _cases(db, id="case-refund-1")[0]
    assert case.status == "resolved"
    assert case.resolved_at is not None
    assert "refund_settled" in [call[1] for call in notifier.calls]


def test_settlement_leaves_a_case_open_without_evidence(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    db.add(
        PaymentCase(
            id="case-refund-1",
            payment_id="pay-1",
            user_id="user-1",
            type="refund",
            status="awaiting_provider",
            assignee_role="support_operations_agent",
            opened_at=NOW,
            updated_at=NOW,
        )
    )
    db.flush()
    rail.add_payment("pay-1", status="succeeded")
    assert refunds.settle_refund_cases(db, rail, audit=audit, notifier=notifier) == []
    assert _cases(db, id="case-refund-1")[0].status == "awaiting_provider"


def test_the_refund_key_is_stable_across_retries() -> None:
    assert refunds.refund_idempotency_key("pay-1", "rail-1") == "refund:rail-1"
    assert refunds.refund_idempotency_key("pay-1", None) == "refund:pay-1"


# --- windows: case service-window escalation (FEAT-009) -------------------


def _seed_case(
    db: Session,
    *,
    case_id: str,
    case_type: str,
    status: str,
    opened_at: datetime,
    payment_id: str = "pay-1",
) -> None:
    db.add(
        PaymentCase(
            id=case_id,
            payment_id=payment_id,
            user_id="user-1",
            type=case_type,
            status=status,
            assignee_role="support_operations_agent",
            opened_at=opened_at,
            updated_at=opened_at,
        )
    )
    db.flush()


def test_a_case_past_its_window_is_planned_for_escalation(db: Session) -> None:
    # A refund window is 5 business days; opened Monday, so the following
    # Tuesday is past it.
    _seed_case(
        db,
        case_id="case-window-1",
        case_type="refund",
        status="awaiting_provider",
        opened_at=datetime(2026, 9, 28, 9, 0),
    )
    plans = windows.plan_escalations(windows.load_active_cases(db), NAIVE_NOW)
    assert [plan.case_id for plan in plans] == ["case-window-1"]


def test_a_case_within_its_window_is_not_escalated(db: Session) -> None:
    _seed_case(
        db,
        case_id="case-window-2",
        case_type="refund",
        status="awaiting_provider",
        opened_at=datetime(2026, 10, 5, 9, 0),
    )
    assert windows.plan_escalations(windows.load_active_cases(db), NAIVE_NOW) == []


def test_escalation_moves_the_case_and_notifies_the_user(
    db: Session, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    _seed_case(
        db,
        case_id="case-window-3",
        case_type="failed_no_delivery",
        status="awaiting_provider",
        opened_at=datetime(2026, 9, 30, 9, 0),
    )
    applied = windows.run_case_escalation(db, audit=audit, notifier=notifier, now=NAIVE_NOW)
    assert [plan.case_id for plan in applied] == ["case-window-3"]
    case = _cases(db, id="case-window-3")[0]
    assert case.status == "escalated"
    assert notifier.calls[0][0] == "user-1"
    assert audit.entries()[0].action == "case.escalated"


def test_a_resolved_case_never_escalates(
    db: Session, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    _seed_case(
        db,
        case_id="case-window-4",
        case_type="refund",
        status="resolved",
        opened_at=datetime(2026, 1, 1, 9, 0),
    )
    assert windows.run_case_escalation(db, audit=audit, notifier=notifier, now=NAIVE_NOW) == []


# --- the scheduled cycle ---------------------------------------------------


def test_scheduled_jobs_reconcile_refund_and_escalate_in_one_pass(
    db: Session, rail: FakeRail, audit: InMemoryAuditLog, notifier: RecordingNotifier
) -> None:
    rail.add_payment("pay-1", status="succeeded")
    _seed_case(
        db,
        case_id="case-old-refund",
        case_type="refund",
        status="awaiting_provider",
        payment_id="pay-old",
        opened_at=datetime(2026, 9, 28, 9, 0),
    )
    report = run_scheduled_jobs(
        db,
        InMemoryPaymentSource([_payment()]),
        InMemoryStatementSource([]),
        audit=audit,
        notifier=notifier,
        payment_lookup=rail,
        refund_port=rail,
        now=NAIVE_NOW,
    )
    # The undelivered debit is cased and refunded, and the stale case escalates.
    assert report.reconciliation.exception_cases_opened == 1
    assert report.reconciliation.refunds_initiated == 1
    assert report.escalations == 1
    by_status = {case.id: (case.type, case.status) for case in _cases(db)}
    assert ("failed_no_delivery", "open") in by_status.values()
    assert by_status["case-old-refund"] == ("refund", "escalated")
