"""Phase 2 integration and acceptance: payment flows beyond the core loop.

Covers the delivered whole for identity verification (FEAT-002), federal
government flows (FEAT-006), everyday bills (FEAT-007), receipts (FEAT-008),
and payment status, failure, and refund handling (FEAT-009) against the frozen
contracts C-020..C-035. Each endpoint is exercised on the assembled API service,
with the in-memory boundaries a deployment binds on ``app.state``.

Reference: features.md FEAT-002/006/007/008/009, user-flow.md Flows 2/3/5/6,
CONTRACTS.md C-020..C-035.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.payments_port import PaymentEventView, PaymentView


def _payment_view(
    *,
    payment_id: str,
    user_id: str,
    status: str = "succeeded",
    amount: int = 5_000,
    payee: str = "Ikeja Electricity Distribution Company",
    service_id: str = "svc-electric",
    reference: str | None = "SBX-RAIL-1",
) -> PaymentView:
    now = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    return PaymentView(
        payment_id=payment_id,
        user_id=user_id,
        service_id=service_id,
        reference=reference,
        payee=payee,
        amount=amount,
        currency="NGN",
        status=status,
        channel="app",
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# FEAT-002 / C-020..C-022: identity verification for regulated payments.
# --------------------------------------------------------------------------- #


def test_identity_verification_status_reflects_the_account(
    signed_in_user, api_client, db_session_factory
):
    """FEAT-002: a verified user is not asked to verify again.

    The verification surface reads the account's stored status; a verified
    account returns it without a repeat check.
    """

    from app.db.models import User

    with db_session_factory() as db:
        user = db.get(User, signed_in_user)
        user.kyc_status = "verified"
        db.commit()

    body = api_client.get("/v1/account/verification").json()
    assert body["kycStatus"] == "verified"


def test_identity_verification_masks_the_identifier(signed_in_user, api_client, db_session_factory):
    """FEAT-002 / NFR-043: the NIN is used for verification, never echoed raw."""

    submitted = api_client.post(
        "/v1/identity/verifications",
        json={"method": "nin", "identifier": "12345678901"},
    )
    assert submitted.status_code == 202, submitted.text
    body = submitted.json()
    assert set(body) == {"verificationId", "status"}
    assert body["status"] in {"pending", "verified", "failed", "corrected"}

    detail = api_client.get(f"/v1/identity/verifications/{body['verificationId']}")
    assert detail.status_code == 200
    serialised = detail.text
    assert "12345678901" not in serialised, "the raw NIN was returned on the wire"


# --------------------------------------------------------------------------- #
# FEAT-006 / C-030..C-032: federal government payment flows.
# --------------------------------------------------------------------------- #


def _seed_federal_collection(db_session_factory, service_id: str, **overrides):
    from app.federal.models import FederalCollection

    values = {
        "service_id": service_id,
        "account_reference": "TREASURY-001",
        "requires_reference": False,
        "instructions": "Pay through the approved channel.",
        "reference_instructions": "Obtain an assessment number from the agency.",
        "status": "current",
    }
    values.update(overrides)
    with db_session_factory() as db:
        db.add(FederalCollection(**values))
        db.commit()


def test_federal_prepare_explains_a_missing_required_reference(
    signed_in_user, api_client, seed_service, db_session_factory
):
    """FEAT-006 acceptance 3: a required reference is explained, not paid around."""

    service_id = seed_service(type="government", name="FIRS", collecting_body="FIRS")
    _seed_federal_collection(db_session_factory, service_id, requires_reference=True)

    body = api_client.post("/v1/payments/federal/prepare", json={"serviceId": service_id}).json()
    assert body["requiresReference"] is True
    assert body["instructions"], "the user must be told how to obtain the reference"


def test_federal_prepare_reports_a_switched_collection_account(
    signed_in_user, api_client, seed_service, db_session_factory
):
    """FEAT-006 alternate G: a stale agency account is a conflict, never paid."""

    service_id = seed_service(type="government", name="FIRS", collecting_body="FIRS")
    _seed_federal_collection(db_session_factory, service_id, status="changed")

    response = api_client.post("/v1/payments/federal/prepare", json={"serviceId": service_id})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "conflict"


def test_federal_receipt_awaits_the_official_receipt_then_stores_it(
    signed_in_user, api_client, phase2_ports
):
    """FEAT-006 acceptance 2: succeeded but no FTeR yet is a hold, not a failure."""

    from app.federal.ports import FederalReceiptView, InMemoryReceiptSource

    lookup = phase2_ports["lookup"]
    lookup.add(_payment_view(payment_id="pay-federal", user_id=signed_in_user, status="succeeded"))
    api_client.app.state.federal_receipt_source = InMemoryReceiptSource()

    pending = api_client.get("/v1/payments/federal/pay-federal/receipt")
    assert pending.status_code == 202, pending.text
    assert pending.json()["status"] == "awaiting_receipt"

    # The central platform issues the FTeR; the next poll stores and returns it.
    source = InMemoryReceiptSource()
    source.add(
        "pay-federal",
        FederalReceiptView(
            receipt_number="FTER-2026-0001",
            verification_status="verified",
            document_ref="s3://fter/0001.pdf",
        ),
    )
    api_client.app.state.federal_receipt_source = source

    stored = api_client.get("/v1/payments/federal/pay-federal/receipt")
    assert stored.status_code == 200, stored.text
    body = stored.json()
    assert body["receiptNumber"] == "FTER-2026-0001"
    assert body["verificationStatus"] == "verified"


def test_federal_receipt_is_a_conflict_when_the_payment_did_not_succeed(
    signed_in_user, api_client, phase2_ports
):
    """C-031: only a settled federal payment has an official receipt."""

    phase2_ports["lookup"].add(
        _payment_view(payment_id="pay-failed", user_id=signed_in_user, status="failed")
    )
    response = api_client.get("/v1/payments/federal/pay-failed/receipt")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_federal_reconcile_opens_one_case_per_payment(signed_in_user, api_client, phase2_ports):
    """FEAT-006 edge: rail confirms but the agency record does not -> one case."""

    phase2_ports["lookup"].add(_payment_view(payment_id="pay-rec", user_id=signed_in_user))

    first = api_client.post(
        "/v1/payments/federal/pay-rec/reconcile", json={"reason": "Agency record missing."}
    )
    assert first.status_code == 202, first.text
    assert first.json()["caseId"]

    duplicate = api_client.post("/v1/payments/federal/pay-rec/reconcile", json={"reason": "Again."})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


# --------------------------------------------------------------------------- #
# FEAT-007 / C-033..C-035: everyday bill flows.
# --------------------------------------------------------------------------- #


def test_bill_validate_reports_an_unknown_recipient_without_erroring(
    signed_in_user, api_client, seed_service, bill_ports
):
    """FEAT-007: a wrong meter number is caught before any debit."""

    service_id = seed_service(type="biller")
    bill_ports["biller"].register(service_id=service_id, recipient="0123456789")

    body = api_client.post(
        "/v1/payments/bills/validate",
        json={"serviceId": service_id, "recipientIdentifier": "9999999999"},
    ).json()
    assert body["valid"] is False
    assert body["reason"]


def test_bill_pay_returns_the_token_and_stores_a_receipt(
    signed_in_user, api_client, seed_service, bill_ports, phase2_ports
):
    """FEAT-007 acceptance 1: the token is returned and stored with the receipt."""

    from app.bills.ports import BillPaymentResult

    service_id = seed_service(type="biller")
    bill_ports["biller"].register(service_id=service_id, recipient="0123456789")
    bill_ports["payments"].set_result(
        BillPaymentResult(
            payment_id="pay-bill-1", status="succeeded", token="TOKEN-9", reference="SBX-1"
        )
    )
    phase2_ports["lookup"].add(
        _payment_view(payment_id="pay-bill-1", user_id=signed_in_user, reference="SBX-1")
    )

    paid = api_client.post(
        "/v1/payments/bills",
        json={
            "serviceId": service_id,
            "recipientIdentifier": "0123456789",
            "amount": 2_000,
            "currency": "NGN",
        },
        headers={"Idempotency-Key": "bill-1"},
    )
    assert paid.status_code == 201, paid.text
    body = paid.json()
    assert body["token"] == "TOKEN-9"
    assert body["receiptId"]

    token = api_client.get(f"/v1/payments/bills/{body['paymentId']}/token")
    assert token.status_code == 200
    assert token.json()["token"] == "TOKEN-9"


def test_bill_offline_biller_prevents_payment(signed_in_user, api_client, seed_service, bill_ports):
    """FEAT-007 acceptance 3: an offline biller prevents the payment."""

    service_id = seed_service(type="biller")
    bill_ports["biller"].register(service_id=service_id, recipient="0123456789")
    bill_ports["biller"].set_offline(True)

    response = api_client.post(
        "/v1/payments/bills",
        json={
            "serviceId": service_id,
            "recipientIdentifier": "0123456789",
            "amount": 2_000,
            "currency": "NGN",
        },
        headers={"Idempotency-Key": "bill-offline"},
    )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "biller_unavailable"
    assert bill_ports["payments"].calls == [], "the rail was asked after the biller was offline"


def test_bill_token_of_a_failed_payment_is_a_conflict_with_the_reason(
    signed_in_user, api_client, bill_ports
):
    """C-035 revision 1: a failed bill must not poll forever."""

    lookup = bill_ports["lookup"]
    lookup.add(_payment_view(payment_id="pay-bill-failed", user_id=signed_in_user, status="failed"))
    lookup.add_event(
        PaymentEventView(
            event_id="ev-1",
            payment_id="pay-bill-failed",
            status="failed",
            actor="rail",
            occurred_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            detail="The biller declined the payment.",
        )
    )

    response = api_client.get("/v1/payments/bills/pay-bill-failed/token")
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["details"]["status"] == "failed"
    assert error["details"]["reason"] == "The biller declined the payment."


# --------------------------------------------------------------------------- #
# FEAT-008 / C-023..C-025: verifiable receipt capture and retrieval.
# --------------------------------------------------------------------------- #


def test_a_completed_bill_payment_yields_a_searchable_receipt(
    signed_in_user, api_client, seed_service, bill_ports, phase2_ports
):
    """FEAT-008 acceptance 1 and 2: a captured receipt is stored and searchable."""

    from app.bills.ports import BillPaymentResult

    service_id = seed_service(type="biller", name="Ikeja Electric")
    bill_ports["biller"].register(service_id=service_id, recipient="0123456789")
    bill_ports["payments"].set_result(
        BillPaymentResult(
            payment_id="pay-receipt", status="succeeded", token="TOKEN-R", reference="SBX-R"
        )
    )
    phase2_ports["lookup"].add(
        _payment_view(
            payment_id="pay-receipt",
            user_id=signed_in_user,
            payee="Ikeja Electricity Distribution Company",
            reference="SBX-R",
        )
    )

    paid = api_client.post(
        "/v1/payments/bills",
        json={
            "serviceId": service_id,
            "recipientIdentifier": "0123456789",
            "amount": 2_000,
            "currency": "NGN",
        },
        headers={"Idempotency-Key": "receipt-1"},
    )
    assert paid.status_code == 201

    listed = api_client.get("/v1/receipts").json()
    assert [r["receiptId"] for r in listed["receipts"]] == [paid.json()["receiptId"]]
    found = api_client.get("/v1/receipts", params={"q": "SBX-R"}).json()
    assert [r["receiptId"] for r in found["receipts"]] == [paid.json()["receiptId"]]
    assert found["receipts"][0]["kind"] == "token"


def test_receipt_detail_shows_the_verified_official_identifier(
    signed_in_user, api_client, phase2_ports, db_session_factory
):
    """FEAT-008 acceptance 3: an official identifier is shown as verified."""

    from app.receipts.service import capture_receipt

    phase2_ports["lookup"].add(_payment_view(payment_id="pay-official", user_id=signed_in_user))
    with db_session_factory() as db:
        receipt = capture_receipt(
            db,
            payment_id="pay-official",
            user_id=signed_in_user,
            kind="official_e_receipt",
            receipt_number="FTER-1",
            verification_status="verified",
            document_ref="s3://fter/1.pdf",
        )
        db.commit()
        receipt_id = receipt.id

    body = api_client.get(f"/v1/receipts/{receipt_id}").json()
    assert body["receipt"]["receiptNumber"] == "FTER-1"
    assert body["receipt"]["verificationStatus"] == "verified"


# --------------------------------------------------------------------------- #
# FEAT-009 / C-026..C-029: status, failure, and refund handling.
# --------------------------------------------------------------------------- #


def _seed_case(db_session_factory, *, payment_id: str, user_id: str, status: str = "open"):
    from app.db.models import PaymentCase

    with db_session_factory() as db:
        case = PaymentCase(
            payment_id=payment_id,
            user_id=user_id,
            type="failed_no_delivery",
            status=status,
            assignee_role="support_operations_agent",
            opened_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case.id


def test_case_detail_shows_the_state_the_timeline_and_the_last_update(
    signed_in_user, api_client, phase2_ports, db_session_factory
):
    """FEAT-009 acceptance 1: a pending payment shows its state and last update."""

    lookup = phase2_ports["lookup"]
    case_id = _seed_case(db_session_factory, payment_id="pay-pending", user_id=signed_in_user)
    lookup.add(_payment_view(payment_id="pay-pending", user_id=signed_in_user, status="pending"))
    lookup.add_event(
        PaymentEventView(
            event_id="ev-1",
            payment_id="pay-pending",
            status="pending",
            actor="rail",
            occurred_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
            detail="Awaiting the rail.",
        )
    )

    body = api_client.get(f"/v1/cases/{case_id}").json()
    assert body["case"]["status"] == "open"
    assert body["payment"]["status"] == "pending"
    assert body["timeline"][0]["status"] == "pending"


def test_refund_of_a_settled_payment_returns_a_reference_and_opens_a_case(
    signed_in_user, api_client, phase2_ports, db_session_factory
):
    """FEAT-009 acceptance 2: a debited-but-not-delivered payment is refunded."""

    phase2_ports["lookup"].add(
        _payment_view(payment_id="pay-refund", user_id=signed_in_user, status="succeeded")
    )

    response = api_client.post(
        "/v1/payments/pay-refund/refund",
        json={"reason": "The biller did not deliver."},
        headers={"Idempotency-Key": "refund-1"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "reversed"
    assert body["refundReference"] == "SBX-RF-1"

    cases = api_client.get("/v1/cases").json()
    types = [case["type"] for case in cases["cases"]]
    assert "refund" in types, "a refund should open a case keyed by the payment"


def test_a_second_refund_for_the_same_payment_is_blocked(signed_in_user, api_client, phase2_ports):
    """FEAT-009 edge: a duplicate refund is detected and blocked."""

    phase2_ports["lookup"].add(
        _payment_view(payment_id="pay-dup-refund", user_id=signed_in_user, status="succeeded")
    )

    first = api_client.post(
        "/v1/payments/pay-dup-refund/refund",
        json={"reason": "Not delivered."},
        headers={"Idempotency-Key": "refund-a"},
    )
    assert first.status_code == 202

    second = api_client.post(
        "/v1/payments/pay-dup-refund/refund",
        json={"reason": "Trying again."},
        headers={"Idempotency-Key": "refund-b"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_dispute_opens_a_case_and_a_second_dispute_conflicts(
    signed_in_user, api_client, phase2_ports, db_session_factory
):
    """FEAT-008/009: a dispute preserves the original and is opened once."""

    phase2_ports["lookup"].add(_payment_view(payment_id="pay-dispute", user_id=signed_in_user))
    case_id = _seed_case(db_session_factory, payment_id="pay-dispute", user_id=signed_in_user)

    first = api_client.post(f"/v1/cases/{case_id}/dispute", json={"reason": "I was charged twice."})
    assert first.status_code == 201, first.text
    assert first.json()["caseId"] != case_id

    duplicate = api_client.post(f"/v1/cases/{case_id}/dispute", json={"reason": "Again."})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"
