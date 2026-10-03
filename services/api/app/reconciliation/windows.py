"""Case service-window escalation job (FEAT-009).

operations.md fixes a service window per case type while a case is in
``awaiting_provider``; a case that exceeds it escalates to the payment partner
rather than sitting open silently. FEAT-009's acceptance criterion is that a
case awaiting the biller escalates when the biller does not respond within the
window, and the user is told.

The window arithmetic and the case state machine live in
``app.cases.lifecycle``; this job selects the cases to escalate and applies the
transition. It is a thin, pure planner over the lifecycle rules plus a runner
that writes the case and appends the audit entry, so the decision is testable
without a scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases import repository as cases_repository
from app.cases.lifecycle import ACTIVE_CASE_STATUSES, find_breaches
from app.core.audit import AuditLog
from app.core.time import utcnow
from app.db.models import PaymentCase
from app.reconciliation.ports import Notifier

# A window breach escalates the case; the audit entry names the automated actor
# so the log does not read as an operator action.
WINDOW_JOB_ACTOR = "system:reconciliation"
ESCALATION_NOTIFICATION = "case_escalated"


@dataclass(frozen=True, slots=True)
class EscalationPlan:
    """One case past its window, ready to escalate."""

    case_id: str
    user_id: str
    case_type: str
    deadline: datetime


def plan_escalations(cases: list[PaymentCase], now: datetime) -> list[EscalationPlan]:
    """The active cases past their service window, newest breach first is not
    guaranteed; the order follows the input list."""
    breaches = find_breaches(cases, now)
    by_id = {case.id: case for case in cases}
    plans: list[EscalationPlan] = []
    for breach in breaches:
        case = by_id[breach.case_id]
        plans.append(
            EscalationPlan(
                case_id=case.id,
                user_id=case.user_id,
                case_type=case.type,
                deadline=breach.deadline,
            )
        )
    return plans


def load_active_cases(db: Session) -> list[PaymentCase]:
    """Every case still being worked, across all owners.

    The escalation job is a system sweep, so it is not user-scoped; it only
    moves a case that is already past its documented window.
    """
    stmt = select(PaymentCase).where(PaymentCase.status.in_(tuple(ACTIVE_CASE_STATUSES)))
    return list(db.execute(stmt).scalars())


def run_case_escalation(
    db: Session,
    *,
    audit: AuditLog,
    notifier: Notifier,
    now: datetime | None = None,
) -> list[EscalationPlan]:
    """Escalate every active case past its window, notify the user, and audit.

    Returns the escalations applied. The case is moved to ``escalated`` and its
    ``updated_at`` advanced; the original ``opened_at`` is preserved so the
    window can still be recomputed for the record.
    """
    moment = now or utcnow()
    plans = plan_escalations(load_active_cases(db), moment)
    if not plans:
        return []

    applied: list[EscalationPlan] = []
    for plan in plans:
        case = cases_repository.get_case(db, plan.case_id)
        if case is None:  # pragma: no cover - the row was just read
            continue
        case.status = "escalated"
        case.updated_at = moment
        notifier.notify(
            user_id=plan.user_id,
            template=ESCALATION_NOTIFICATION,
            detail=f"Your {plan.case_type.replace('_', ' ')} case needs the payment partner.",
        )
        audit.append(
            "case.escalated",
            actor_id=None,
            actor_role=WINDOW_JOB_ACTOR,
            target=plan.case_id,
            reason=f"The {plan.case_type} service window passed.",
            detail={"caseType": plan.case_type, "deadline": plan.deadline.isoformat()},
        )
        applied.append(plan)

    db.flush()
    return applied


__all__ = [
    "ESCALATION_NOTIFICATION",
    "WINDOW_JOB_ACTOR",
    "EscalationPlan",
    "load_active_cases",
    "plan_escalations",
    "run_case_escalation",
]
