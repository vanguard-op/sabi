"""Reconciliation and refund job entry points (FEAT-006, FEAT-007, FEAT-009).

This is the layer a scheduler calls. It composes the pure rules with the
primary store, the audit log, and the notification port:

- ``run_daily_reconciliation`` matches a window of internal payments against the
  rail, agency, and treasury statements and opens exception cases for the
  unmatched or mismatched items (operations.md, "Reconciliation operations").
- ``run_case_escalation`` escalates active cases past their service window
  (FEAT-009; ``app.reconciliation.windows``).
- ``run_refund_sweep`` refunds failed-no-delivery payments exactly once and
  tracks each refund case to acknowledgement (FEAT-009;
  ``app.reconciliation.refunds``).

A payment debited but not delivered is refunded automatically when it is
detected: pass the refund boundary to ``run_daily_reconciliation`` and every
``failed_no_delivery`` it opens also goes through the refund sweep
(FEAT-009; FEAT-007's "biller rejects after rail debit" edge).

An exception case is opened once per underlying condition: the job checks for an
existing open case of the same type for the payment before creating another, so
a retried run does not multiply cases. A federal exception escalates on the spot
rather than waiting out the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.cases import repository as cases_repository
from app.cases.schemas import SUPPORT_OPERATIONS_ROLE
from app.core.audit import AuditLog
from app.core.time import utcnow
from app.payments_port import PaymentLookup, RefundPort
from app.reconciliation import repository, rules, windows
from app.reconciliation.ports import Notifier, PaymentSource, StatementSource
from app.reconciliation.refunds import run_refund_sweep, settle_refund_cases
from app.reconciliation.rules import ExceptionType, ReconciliationException

RECONCILIATION_JOB_ACTOR = "system:reconciliation"
CASE_OPENED_NOTIFICATION = "case_opened"

# Case types this job may open; a condition already tracked by an open case of
# the same type is not reopened.
JOB_CASE_TYPES = frozenset(
    {
        ExceptionType.FAILED_NO_DELIVERY.value,
        ExceptionType.DISPUTED.value,
        ExceptionType.RECEIPT_MISSING.value,
    }
)


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """What one reconciliation run did, for logging and operator review."""

    window_start: datetime
    window_end: datetime
    payments_checked: int
    matched: int
    exception_cases_opened: int
    exceptions_deferred: int
    refunds_initiated: int = 0


def run_daily_reconciliation(
    db: Session,
    payment_source: PaymentSource,
    statement_source: StatementSource,
    *,
    audit: AuditLog,
    notifier: Notifier,
    payment_lookup: PaymentLookup | None = None,
    refund_port: RefundPort | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    now: datetime | None = None,
) -> ReconciliationReport:
    """Reconcile one window of payments against the statements.

    Defaults to the previous 24 hours ending at ``now``. Every exception that
    maps to an internal payment opens (at most) one case; an orphan statement
    line with no internal payment is audited for operator follow-up, since a
    case must belong to a payment.

    When both ``payment_lookup`` and ``refund_port`` are supplied, a payment
    detected as debited without delivery is refunded as well as cased, so the
    automatic refund in FEAT-009 happens at the moment of detection rather than
    waiting for a separate trigger. Without them the run is read-only and
    opens the exception case alone.
    """
    moment = now or utcnow()
    window_end = until or moment
    window_start = since or (window_end - timedelta(days=1))

    payments = payment_source.payments(since=window_start, until=window_end)
    statements = statement_source.statements(since=window_start, until=window_end)
    items, exceptions = rules.correlate(payments, statements)

    matched = sum(1 for item in items if item.outcome is rules.MatchOutcome.MATCHED)
    opened = 0
    deferred = 0
    refunds_initiated = 0
    for exception in exceptions:
        opened_here = _open_exception_case(db, exception, audit=audit, notifier=notifier)
        if opened_here:
            opened += 1
        else:
            deferred += 1
        if (
            opened_here
            and exception.case_type is ExceptionType.FAILED_NO_DELIVERY
            and exception.user_id
            and payment_lookup is not None
            and refund_port is not None
        ):
            settled = run_refund_sweep(
                db,
                payment_lookup,
                refund_port,
                user_id=exception.user_id,
                payment_ids=[exception.payment_id],
                audit=audit,
                notifier=notifier,
            )
            refunds_initiated += len(settled)

    report = ReconciliationReport(
        window_start=window_start,
        window_end=window_end,
        payments_checked=len(payments),
        matched=matched,
        exception_cases_opened=opened,
        exceptions_deferred=deferred,
        refunds_initiated=refunds_initiated,
    )
    audit.append(
        "reconciliation.run",
        actor_id=None,
        actor_role=RECONCILIATION_JOB_ACTOR,
        target=None,
        reason="Daily reconciliation completed.",
        detail={
            "windowStart": window_start.isoformat(),
            "windowEnd": window_end.isoformat(),
            "paymentsChecked": len(payments),
            "matched": matched,
            "casesOpened": opened,
            "deferred": deferred,
            "refundsInitiated": refunds_initiated,
        },
    )
    db.flush()
    return report


def _open_exception_case(
    db: Session,
    exception: ReconciliationException,
    *,
    audit: AuditLog,
    notifier: Notifier,
) -> bool:
    """Open the exception's case unless it is already tracked.

    Returns True when a case was opened, False when it was deferred (an orphan
    with no owner, or a condition already tracked).
    """
    if not exception.user_id:
        # An orphan statement line has no account to attach a case to; it is
        # recorded for the reconciliation officer instead of fabricated onto a
        # payment that does not exist.
        audit.append(
            "reconciliation.exception",
            actor_id=None,
            actor_role=RECONCILIATION_JOB_ACTOR,
            target=exception.reference,
            reason=exception.reason,
            detail={"caseType": str(exception.case_type)},
        )
        return False

    if (
        repository.find_open_case_for_payment(
            db, exception.payment_id, case_type=str(exception.case_type)
        )
        is not None
    ):
        return False

    status = "escalated" if exception.escalate else "open"
    case = cases_repository.create_case(
        db,
        payment_id=exception.payment_id,
        user_id=exception.user_id,
        case_type=str(exception.case_type),
        status=status,
        assignee_role=_assignee_role(exception.case_type),
    )
    if exception.escalate:
        case.resolved_at = None
    audit.append(
        "reconciliation.exception",
        actor_id=None,
        actor_role=RECONCILIATION_JOB_ACTOR,
        target=case.id,
        reason=exception.reason,
        detail={
            "caseType": str(exception.case_type),
            "paymentId": exception.payment_id,
            "reference": exception.reference,
            "escalated": exception.escalate,
        },
    )
    notifier.notify(
        user_id=exception.user_id,
        template=CASE_OPENED_NOTIFICATION,
        detail="We opened a case for a payment that did not reconcile.",
    )
    return True


def _assignee_role(case_type: ExceptionType | str) -> str:
    # A federal or disputed item goes to the reconciliation officer; a delivery
    # or receipt exception starts with support operations.
    if str(case_type) in (ExceptionType.DISPUTED.value,):
        return "reconciliation_officer"
    return SUPPORT_OPERATIONS_ROLE


@dataclass(frozen=True, slots=True)
class JobCycleReport:
    """The combined outcome of one scheduled job cycle."""

    reconciliation: ReconciliationReport
    escalations: int
    refunds_settled: int


def run_scheduled_jobs(
    db: Session,
    payment_source: PaymentSource,
    statement_source: StatementSource,
    *,
    audit: AuditLog,
    notifier: Notifier,
    payment_lookup: PaymentLookup,
    refund_port: RefundPort,
    now: datetime | None = None,
) -> JobCycleReport:
    """Run the reconciliation, refund-tracking, and escalation jobs in one pass.

    This is the single entry point a scheduler calls: it reconciles the daily
    window (auto-refunding any debit with no delivery), settles the refund cases
    the rail has since acknowledged, and escalates the cases past their service
    window. Each job is idempotent, so an at-least-once queue delivery is safe.
    """
    reconciliation = run_daily_reconciliation(
        db,
        payment_source,
        statement_source,
        audit=audit,
        notifier=notifier,
        payment_lookup=payment_lookup,
        refund_port=refund_port,
        now=now,
    )
    refunds_settled = settle_refund_cases(
        db, payment_lookup, audit=audit, notifier=notifier, now=now
    )
    escalations = windows.run_case_escalation(db, audit=audit, notifier=notifier, now=now)
    return JobCycleReport(
        reconciliation=reconciliation,
        escalations=len(escalations),
        refunds_settled=len(refunds_settled),
    )


__all__ = [
    "JOB_CASE_TYPES",
    "CASE_OPENED_NOTIFICATION",
    "RECONCILIATION_JOB_ACTOR",
    "JobCycleReport",
    "ReconciliationReport",
    "run_daily_reconciliation",
    "run_scheduled_jobs",
]
