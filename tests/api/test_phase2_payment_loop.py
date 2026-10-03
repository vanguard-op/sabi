"""Phase 2 integration and acceptance: the payment loop.

This is the cross-service layer the per-module unit suites do not provide: it
assembles the real API gateway and the real isolated payment module in one
process and drives the frozen C-017..C-019 boundary between them over HTTP.
The gateway's own unit tests stop at a body double; here the actual module
signs the mandate, enforces the authorisation limit, and dedupes by
idempotency key, so the acceptance criteria for FEAT-005 (payment authorisation
and execution) and NFR-027 (a mandate bound to amount, payee, and user, verified
before execution) are proven on the delivered whole.

Reference: CONTRACTS.md C-017..C-019, features.md FEAT-005, user-flow.md Flow 2,
nfr.md NFR-027, DELIVERY.md Definition of Done.
"""

from __future__ import annotations


def _authorise(client, service_id: str, *, amount: int = 5_000, **overrides):
    body = {
        "serviceId": service_id,
        "amount": amount,
        "currency": "NGN",
        "channel": "app",
    }
    body.update(overrides)
    headers = {}
    if "Idempotency-Key" in overrides:
        headers["Idempotency-Key"] = overrides.pop("Idempotency-Key")
    return client.post("/v1/payments/authorise", json=body, headers=headers)


# --------------------------------------------------------------------------- #
# C-017..C-019 through the real gateway -> payment-module hop.
# --------------------------------------------------------------------------- #


def test_authorise_and_execute_complete_a_payment_through_the_real_hop(
    signed_in_user, api_client, live_payment_module, seed_service
):
    """FEAT-005 acceptance 1: authorise, execute, and a transaction reference.

    The payment travels gateway -> payment module over the C-017/C-018 HTTP
    boundary, so the module's own mandate signing and execution state are what
    return the reference.
    """

    service_id = seed_service()

    authorised = _authorise(api_client, service_id, amount=5_000, secondConfirmation=False)
    assert authorised.status_code == 201, authorised.text
    body = authorised.json()
    assert set(body) == {"paymentId", "status", "mandateId", "railReference"}
    assert body["status"] == "authorized"
    assert body["mandateId"]
    assert body["railReference"] is None

    executed = api_client.post(
        f"/v1/payments/{body['paymentId']}/execute",
        json={"mandateId": body["mandateId"]},
        headers={"Idempotency-Key": "exec-1"},
    )
    assert executed.status_code == 200, executed.text
    result = executed.json()
    assert result["paymentId"] == body["paymentId"]
    assert result["status"] == "succeeded"
    assert result["railReference"]

    listed = api_client.get("/v1/payments").json()
    assert [p["paymentId"] for p in listed["payments"]] == [body["paymentId"]]
    assert listed["payments"][0]["status"] == "succeeded"
    assert listed["payments"][0]["payee"] == "Ikeja Electricity Distribution Company"


def test_duplicate_execution_returns_the_first_reference_without_a_second_charge(
    signed_in_user, api_client, live_payment_module, seed_service, payment_rail
):
    """FEAT-005 edge case: a double tap or retried session executes once."""

    service_id = seed_service()
    authorised = _authorise(api_client, service_id).json()

    first = api_client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={"Idempotency-Key": "exec-dup"},
    )
    second = api_client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={"Idempotency-Key": "exec-dup"},
    )
    assert first.json() == second.json()
    assert first.json()["railReference"]
    assert len(payment_rail.charges) == 1, "the rail was charged more than once"


def test_authorisation_above_the_limit_requires_a_second_confirmation(
    signed_in_user, api_client, live_payment_module, seed_service
):
    """FEAT-005 acceptance 3: above the user's set limit, confirm again.

    The module's default limit is forwarded only when the gateway knows the
    user's own limit; here the module applies its configured default, which is
    where the rule is enforced (C-017 422).
    """

    service_id = seed_service()
    refused = _authorise(api_client, service_id, amount=6_000_000)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_failed"

    allowed = _authorise(api_client, service_id, amount=6_000_000, secondConfirmation=True)
    assert allowed.status_code == 201, allowed.text


def test_a_mandate_does_not_execute_a_payment_for_a_different_amount(
    signed_in_user, api_client, live_payment_module, seed_service, payment_rail
):
    """NFR-027: the mandate is verified against the stored amount and payee.

    A mandate issued for one payment must not execute another payment whose
    amount differs; the module refuses and the rail is never asked.
    """

    service_id = seed_service()
    mandate_for_low = _authorise(api_client, service_id, amount=1_000).json()
    # A second, higher-amount payment: the low mandate does not bind it.
    other = _authorise(api_client, service_id, amount=2_000, secondConfirmation=True).json()

    response = api_client.post(
        f"/v1/payments/{other['paymentId']}/execute",
        json={"mandateId": mandate_for_low["mandateId"]},
        headers={"Idempotency-Key": "exec-mismatch"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "conflict"
    assert payment_rail.charges == [], "the rail was asked to charge a mismatched mandate"


def test_a_changed_amount_breaks_the_mandate_before_execution(
    signed_in_user,
    api_client,
    live_payment_module,
    seed_service,
    payment_rail,
    payment_module_app,
):
    """NFR-027: a mandate is bound to the amount it was signed for.

    The gateway resolves the payee and the module stores the amount at
    authorisation; mutating the stored amount after the mandate is signed must
    make execution refuse, so a changed amount can never be charged.
    """

    from sabi_payments.db.models import Payment

    service_id = seed_service()
    authorised = _authorise(api_client, service_id, amount=1_500).json()

    # Tamper with the stored amount the way a corrupted or substituted record
    # would, then attempt to execute with the genuinely signed mandate.
    with payment_module_app.state.session_factory() as session:
        payment = session.get(Payment, authorised["paymentId"])
        payment.amount = 9_999
        session.commit()

    response = api_client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={"Idempotency-Key": "exec-tampered"},
    )
    assert response.status_code in {409, 422}, response.text
    assert payment_rail.charges == [], "a tampered amount reached the rail"


def test_duplicate_authorisation_returns_the_existing_payment_409(
    signed_in_user, api_client, live_payment_module, seed_service
):
    """FEAT-005 edge case: a retried authorisation resolves to the first payment."""

    service_id = seed_service()
    first = _authorise(api_client, service_id, **{"Idempotency-Key": "auth-1"})
    assert first.status_code == 201
    duplicate = _authorise(api_client, service_id, **{"Idempotency-Key": "auth-1"})
    assert duplicate.status_code == 409, duplicate.text
    error = duplicate.json()["error"]
    assert error["code"] == "conflict"
    assert error["details"]["paymentId"] == first.json()["paymentId"]


def test_payment_listing_filters_by_status(
    signed_in_user, api_client, live_payment_module, seed_service
):
    service_id = seed_service()
    authorised = _authorise(api_client, service_id).json()
    api_client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={"Idempotency-Key": "exec-filter"},
    )

    succeeded = api_client.get("/v1/payments", params={"status": "succeeded"}).json()
    assert all(p["status"] == "succeeded" for p in succeeded["payments"])
    assert succeeded["payments"], "the settled payment should list under its status"


def test_execute_requires_an_idempotency_key_at_the_gateway(
    signed_in_user, api_client, live_payment_module, seed_service
):
    service_id = seed_service()
    authorised = _authorise(api_client, service_id).json()
    response = api_client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_unknown_rail_outcome_is_held_pending_never_retried(
    signed_in_user, api_client, live_payment_module, seed_service, payment_rail
):
    """FEAT-005 / FEAT-009: a rail timeout is held pending, not reported settled.

    The gateway must surface the module's ``pending`` state, and the payment must
    list as pending so the client reconciles rather than retrying blindly.
    """

    from sabi_payments.core.rail import RailOutcome

    service_id = seed_service()
    authorised = _authorise(api_client, service_id).json()
    payment_rail.charge_outcome = RailOutcome(status="pending", reference="SBX-UNKNOWN")

    executed = api_client.post(
        f"/v1/payments/{authorised['paymentId']}/execute",
        json={"mandateId": authorised["mandateId"]},
        headers={"Idempotency-Key": "exec-pending"},
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "pending"

    listed = api_client.get("/v1/payments", params={"status": "pending"}).json()
    assert [p["paymentId"] for p in listed["payments"]] == [authorised["paymentId"]]
