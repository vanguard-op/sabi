"""FEAT-005 service rules: authorise, execute, and the failure edges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from payment_fixtures import FakeRail
from sqlalchemy.orm import Session, sessionmaker

from sabi_payments.core.errors import PaymentError
from sabi_payments.core.mandate import MandateRecord, MandateSigner
from sabi_payments.core.rail import RailOutcome
from sabi_payments.db.models import PaymentMandate
from sabi_payments.payments.service import PaymentService

USER = "user-1"


def authorise(service: PaymentService, **overrides: object):
    args: dict[str, object] = {
        "user_id": USER,
        "service_id": "svc-1",
        "amount": 50_000,
        "currency": "NGN",
        "payee": "Lagos State Internal Revenue",
        "payee_reference": "TIN-123",
        "payment_method_id": None,
        "channel": "app",
        "second_confirmation": False,
        "idempotency_key": None,
        "authorisation_limit": None,
        "service_type": "government",
    }
    args.update(overrides)
    return service.authorise(**args)  # type: ignore[arg-type]


def test_authorise_creates_a_payment_and_a_signed_mandate(
    service: PaymentService, session_factory: sessionmaker[Session]
) -> None:
    result = authorise(service)
    assert result.status == "authorized"
    assert result.rail_reference is None

    with session_factory() as session:
        mandate = session.get(PaymentMandate, result.mandate_id)
    signer = MandateSigner("test-key")
    assert signer.verify_signature(
        MandateRecord(
            id=mandate.id,
            user_id=mandate.user_id,
            amount=mandate.amount,
            currency=mandate.currency,
            payee=mandate.payee,
            payee_reference=mandate.payee_reference,
            nonce=mandate.nonce,
            signature=mandate.signature,
            status=mandate.status,
            expires_at=mandate.expires_at,
        )
    )


def test_zero_amount_is_refused(service: PaymentService) -> None:
    with pytest.raises(PaymentError) as caught:
        authorise(service, amount=0)
    assert caught.value.status_code == 400


def test_above_limit_without_second_confirmation_is_refused(service: PaymentService) -> None:
    with pytest.raises(PaymentError) as caught:
        authorise(service, amount=6_000_000)
    assert caught.value.status_code == 422


def test_above_limit_with_second_confirmation_is_allowed(service: PaymentService) -> None:
    result = authorise(service, amount=6_000_000, second_confirmation=True)
    assert result.status == "authorized"


def test_a_higher_forwarded_limit_avoids_the_confirmation(service: PaymentService) -> None:
    result = authorise(service, amount=6_000_000, authorisation_limit=10_000_000)
    assert result.status == "authorized"


def test_duplicate_authorisation_returns_the_existing_payment(service: PaymentService) -> None:
    first = authorise(service, idempotency_key="key-1")
    with pytest.raises(PaymentError) as caught:
        authorise(service, idempotency_key="key-1")
    assert caught.value.status_code == 409
    assert caught.value.details == {"paymentId": first.payment_id, "railReference": None}


def test_execute_succeeds_and_returns_the_rail_reference(
    service: PaymentService, rail: FakeRail
) -> None:
    authorised = authorise(service)
    result = service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    assert result.status == "succeeded"
    assert result.rail_reference == "RAIL-1"
    assert rail.charges[0].amount == 50_000


def test_execute_replay_returns_the_same_result_without_a_second_charge(
    service: PaymentService, rail: FakeRail
) -> None:
    authorised = authorise(service)
    first = service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    second = service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    assert second == first
    assert len(rail.charges) == 1


def test_execute_with_a_changed_amount_is_refused(service: PaymentService) -> None:
    authorised = authorise(service)
    # Move the stored amount away from what the mandate bound.
    with service._session_factory() as session:  # noqa: SLF001 (test seam)
        from sabi_payments.db.models import Payment

        payment = session.get(Payment, authorised.payment_id)
        payment.amount = 99_000
        session.commit()
    with pytest.raises(PaymentError) as caught:
        service.execute(
            user_id=USER,
            payment_id=authorised.payment_id,
            mandate_id=authorised.mandate_id,
            idempotency_key="exec-1",
        )
    assert caught.value.status_code == 422


def test_unknown_payment_is_not_found(service: PaymentService) -> None:
    with pytest.raises(PaymentError) as caught:
        service.execute(user_id=USER, payment_id="missing", mandate_id="m", idempotency_key="k")
    assert caught.value.status_code == 404


def test_expired_mandate_is_gone(service: PaymentService) -> None:
    authorised = authorise(service)
    with service._session_factory() as session:  # noqa: SLF001 (test seam)
        from sabi_payments.db.models import PaymentMandate

        mandate = session.get(PaymentMandate, authorised.mandate_id)
        mandate.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    with pytest.raises(PaymentError) as caught:
        service.execute(
            user_id=USER,
            payment_id=authorised.payment_id,
            mandate_id=authorised.mandate_id,
            idempotency_key="exec-1",
        )
    assert caught.value.status_code == 410


def test_consumed_mandate_conflicts(service: PaymentService) -> None:
    authorised = authorise(service)
    service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    # A second, distinct execution key against the consumed mandate conflicts.
    with pytest.raises(PaymentError) as caught:
        service.execute(
            user_id=USER,
            payment_id=authorised.payment_id,
            mandate_id=authorised.mandate_id,
            idempotency_key="exec-2",
        )
    assert caught.value.status_code == 409


def test_rail_failure_leaves_the_payment_incomplete(
    service: PaymentService, rail: FakeRail
) -> None:
    rail.outcome = RailOutcome(status="failed", failure_reason="Biller rejected the payment.")
    authorised = authorise(service)
    result = service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    assert result.status == "failed"


def test_unknown_rail_outcome_is_held_pending(service: PaymentService, rail: FakeRail) -> None:
    rail.outcome = RailOutcome(status="pending", failure_reason="No answer from the rail.")
    authorised = authorise(service)
    result = service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    assert result.status == "pending"
    # A pending payment is not charged twice by a replay.
    service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    assert len(rail.charges) == 1


def test_insufficient_funds_maps_to_402(service: PaymentService, rail: FakeRail) -> None:
    rail.outcome = RailOutcome(status="failed", failure_reason="Insufficient funds.")
    authorised = authorise(service)
    with pytest.raises(PaymentError) as caught:
        service.execute(
            user_id=USER,
            payment_id=authorised.payment_id,
            mandate_id=authorised.mandate_id,
            idempotency_key="exec-1",
        )
    assert caught.value.status_code == 402


def test_list_is_scoped_to_the_owner(service: PaymentService) -> None:
    authorise(service)
    authorise(service, user_id="user-2")
    page = service.list_payments(user_id=USER, cursor=None, limit=20, status=None)
    assert len(page.payments) == 1


def test_list_paginates_with_a_cursor(service: PaymentService) -> None:
    for _ in range(3):
        authorise(service)
    first = service.list_payments(user_id=USER, cursor=None, limit=2, status=None)
    assert len(first.payments) == 2
    assert first.next_cursor is not None
    second = service.list_payments(user_id=USER, cursor=first.next_cursor, limit=2, status=None)
    assert len(second.payments) == 1
    assert second.next_cursor is None


def test_list_filters_by_status(service: PaymentService) -> None:
    authorised = authorise(service)
    service.execute(
        user_id=USER,
        payment_id=authorised.payment_id,
        mandate_id=authorised.mandate_id,
        idempotency_key="exec-1",
    )
    authorise(service)
    page = service.list_payments(user_id=USER, cursor=None, limit=20, status="succeeded")
    assert [payment.status for payment in page.payments] == ["succeeded"]


def test_an_invalid_cursor_is_refused(service: PaymentService) -> None:
    with pytest.raises(PaymentError) as caught:
        service.list_payments(user_id=USER, cursor="not-a-cursor", limit=20, status=None)
    assert caught.value.status_code == 400
