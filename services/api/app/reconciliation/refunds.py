"""Refund job: automatic refund, duplicate prevention, and settlement tracking.

FEAT-009 fixes three behaviours this job owns:

- A payment debited but not delivered opens a refund automatically and a case
  (acceptance criterion 2).
- A duplicate refund is detected by reference and the second is blocked
  (edge case), in the case workflow and at the rail boundary (operations.md).
- A refund case tracks the request to rail or biller acknowledgement, and a
  refund the rail confirms resolves the case.

The rail call is the isolated payment module's (``app.cases.ports.RefundPort``);
this job decides *what* to refund, prevents a second attempt, and advances a
tracking case once the rail acknowledges it. It is keyed by the payment
reference, so a retried job run is safe.

The job reads payments through ``app.cases.ports.PaymentLookup`` and refund
history through the case repository, so it needs no direct access to the
isolated payment store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases import repository as cases_repository
from app.cases.schemas import SUPPORT_OPERATIONS_ROLE
from app.cases.service import REFUNDABLE_PAYMENT_STATES, TERMINAL_REFUND_STATES
from app.core.audit import AuditLog
from app.core.time import utcnow
from app.db.models import PaymentCase
from app.payments_port import PaymentLookup, RefundPort
from app.reconciliation.ports import Notifier, NullNotifier

REFUND_JOB_ACTOR = "system:reconciliation"
REFUND_NOTIFICATION = "refund_initiated"
REFUND_SETTLED_NOTIFICATION = "refund_settled"

# The statuses the payment store reports for a refund the rail has settled.
SETTLED_PAYMENT_STATUSES = TERMINAL_REFUND_STATES


class RefundDecision(StrEnum):
    """Why a payment is or is not refunded by the sweep."""

    REFUND = "refund"
    # A refund case already exists for the payment: the duplicate is blocked.
    DUPLICATE = "duplicate"
    # The payment is not in a refundable state, so it is left alone.
    NOT_REFUNDABLE = "not_refundable"


@dataclass(frozen=True, slots=True)
class RefundPlan:
    """The sweep's decision for one payment."""

    payment_id: str
    user_id: str
    reference: str | None
    decision: RefundDecision
    reason: str


@dataclass(frozen=True, slots=True)
class RefundOutcome:
    """The result of one refund request at the rail."""

    payment_id: str
    status: str
    refund_reference: str | None = None


def refund_idempotency_key(payment_id: str, reference: str | None) -> str:
    """The stable key a retried sweep reuses so no second refund executes."""
    return f"refund:{reference or payment_id}"


def plan_refunds(
    db: Session,
    lookup: PaymentLookup,
    *,
    user_id: str,
    payment_ids: list[str],
) -> list[RefundPlan]:
    """Decide, per payment, whether the sweep should refund it.

    A settled payment with no open refund case is refunded; an existing or
    terminal refund is recorded as a blocked duplicate.
    """
    plans: list[RefundPlan] = []
    for payment_id in payment_ids:
        payment = lookup.get(user_id=user_id, payment_id=payment_id)
        if payment is None:
            # A payment that is not there, or belongs to someone else, is not
            # the sweep's to refund (least privilege).
            continue
        if payment.status in SETTLED_PAYMENT_STATUSES:
            plans.append(
                RefundPlan(
                    payment_id=payment_id,
                    user_id=user_id,
                    reference=payment.reference,
                    decision=RefundDecision.DUPLICATE,
                    reason="A refund for this payment has already settled.",
                )
            )
            continue
        if cases_repository.find_open_refund_for_payment(db, payment_id) is not None:
            plans.append(
                RefundPlan(
                    payment_id=payment_id,
                    user_id=user_id,
                    reference=payment.reference,
                    decision=RefundDecision.DUPLICATE,
                    reason="A refund for this payment is already being tracked.",
                )
            )
            continue
        if payment.status not in REFUNDABLE_PAYMENT_STATES:
            plans.append(
                RefundPlan(
                    payment_id=payment_id,
                    user_id=user_id,
                    reference=payment.reference,
                    decision=RefundDecision.NOT_REFUNDABLE,
                    reason="The payment is not in a state that can be refunded.",
                )
            )
            continue
        plans.append(
            RefundPlan(
                payment_id=payment_id,
                user_id=user_id,
                reference=payment.reference,
                decision=RefundDecision.REFUND,
                reason="The payment was debited without delivery.",
            )
        )
    return plans


def run_refund_sweep(
    db: Session,
    lookup: PaymentLookup,
    refund_port: RefundPort,
    *,
    user_id: str,
    payment_ids: list[str],
    audit: AuditLog,
    notifier: Notifier,
) -> list[RefundOutcome]:
    """Refund every failed-no-delivery payment exactly once.

    A refund already tracked or already settled is recorded as a blocked
    duplicate and the rail is not asked; a refund the rail accepts opens the
    tracking case and notifies the user.
    """
    outcomes: list[RefundOutcome] = []
    for plan in plan_refunds(db, lookup, user_id=user_id, payment_ids=payment_ids):
        if plan.decision is RefundDecision.DUPLICATE:
            audit.append(
                "refund.duplicate_blocked",
                actor_id=None,
                actor_role=REFUND_JOB_ACTOR,
                target=plan.payment_id,
                reason=plan.reason,
                detail={"reference": plan.reference},
            )
            continue
        if plan.decision is RefundDecision.NOT_REFUNDABLE:
            continue

        result = refund_port.refund(
            user_id=plan.user_id,
            payment_id=plan.payment_id,
            reason=plan.reason,
            idempotency_key=refund_idempotency_key(plan.payment_id, plan.reference),
        )
        if result.status not in SETTLED_PAYMENT_STATUSES:
            # The rail has not settled the refund; the case stays open and the
            # sweep retries under the same idempotency key rather than doubling.
            continue

        case = cases_repository.create_case(
            db,
            payment_id=plan.payment_id,
            user_id=plan.user_id,
            case_type="refund",
            status="awaiting_provider",
            assignee_role=SUPPORT_OPERATIONS_ROLE,
        )
        audit.append(
            "refund.initiated",
            actor_id=None,
            actor_role=REFUND_JOB_ACTOR,
            target=plan.payment_id,
            reason=plan.reason,
            detail={"reference": plan.reference, "caseId": case.id},
        )
        notifier.notify(
            user_id=plan.user_id,
            template=REFUND_NOTIFICATION,
            detail="A refund for your payment has been started.",
        )
        outcomes.append(
            RefundOutcome(
                payment_id=plan.payment_id,
                status=result.status,
                refund_reference=result.refund_reference,
            )
        )

    db.flush()
    return outcomes


def settle_refund_cases(
    db: Session,
    lookup: PaymentLookup,
    *,
    audit: AuditLog,
    notifier: Notifier | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Resolve refund cases whose refund the rail or biller has acknowledged.

    A refund case sits in ``awaiting_provider`` until the payment store reports
    the payment refunded or reversed; this sweep then resolves the case and
    notifies the user, and returns the resolved case ids. A case with no
    settlement evidence stays open, so it is never closed on a guess.
    """
    moment = now or utcnow()
    notifier = notifier or NullNotifier()
    cases = (
        db.execute(
            select(PaymentCase)
            .where(PaymentCase.type == "refund", PaymentCase.status == "awaiting_provider")
            .order_by(PaymentCase.id.asc())
        )
        .scalars()
        .all()
    )
    resolved: list[str] = []
    for case in cases:
        payment = lookup.get(user_id=case.user_id, payment_id=case.payment_id)
        if payment is None or payment.status not in SETTLED_PAYMENT_STATUSES:
            continue
        case.status = "resolved"
        case.resolved_at = moment
        case.updated_at = moment
        audit.append(
            "refund.settled",
            actor_id=None,
            actor_role=REFUND_JOB_ACTOR,
            target=case.id,
            reason="The rail acknowledged the refund.",
            detail={"paymentId": case.payment_id},
        )
        notifier.notify(
            user_id=case.user_id,
            template=REFUND_SETTLED_NOTIFICATION,
            detail="Your refund has settled.",
        )
        resolved.append(case.id)

    db.flush()
    return resolved


__all__ = [
    "REFUND_JOB_ACTOR",
    "REFUND_NOTIFICATION",
    "REFUND_SETTLED_NOTIFICATION",
    "SETTLED_PAYMENT_STATUSES",
    "RefundDecision",
    "RefundOutcome",
    "RefundPlan",
    "plan_refunds",
    "refund_idempotency_key",
    "run_refund_sweep",
    "settle_refund_cases",
]
