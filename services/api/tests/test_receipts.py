"""Receipt capture and retrieval unit tests (FEAT-008, C-023–C-025).

Covers capture and its idempotency, the list/detail/document contract shapes,
search by reference, agency, and date, the access rules, pagination, and the
errors the contract names.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.ids import new_id
from app.db.models import Receipt
from app.receipts import service
from app.receipts.payments import InMemoryPaymentLookup, PaymentView
from app.receipts.router import router as receipts_router

FIXED_NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def _mounted(app) -> bool:
    """Whether the app factory already mounts the receipts router.

    This module is added to the factory's module list by a separate change; until
    then the tests mount it the same way the factory would. Reading the OpenAPI
    paths is stable across FastAPI's internal router wrapper.
    """
    return any(path.startswith("/v1/receipts") for path in app.openapi().get("paths", {}))


def _payment(
    *,
    payment_id: str | None = None,
    user_id: str = "user-1",
    reference: str | None = "TRX-REF-001",
    payee: str = "Onitsha South LGA",
    amount: int = 25_000,
    status: str = "succeeded",
    created_at: datetime = FIXED_NOW,
) -> PaymentView:
    return PaymentView(
        payment_id=payment_id or new_id(),
        user_id=user_id,
        service_id="service-1",
        reference=reference,
        payee=payee,
        amount=amount,
        currency="NGN",
        status=status,
        channel="app",
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.fixture
def receipts(app, client, db_session_factory, session_manager):
    """A client backed by isolated SQLite, a stub payment lookup, and sign-in."""
    app.state.session_factory = db_session_factory
    lookup = InMemoryPaymentLookup()
    app.state.receipts_payment_lookup = lookup

    # main.py does not yet list this module, so mount it the way the factory
    # does; guard against a double mount once it is listed.
    if not _mounted(app):
        app.include_router(receipts_router, prefix="/v1")

    def add_receipt(
        *,
        payment: PaymentView,
        user_id: str = "user-1",
        kind: str = "official_e_receipt",
        document_ref: str = "https://store.example/receipts/abc.pdf",
        receipt_number: str | None = "FTeR-2026-0001",
        verification_status: str = "verified",
        issued_at: datetime | None = FIXED_NOW,
    ) -> Receipt:
        lookup.add(payment)
        with db_session_factory() as db:
            receipt = service.capture_receipt(
                db,
                payment_id=payment.payment_id,
                user_id=user_id,
                kind=kind,
                document_ref=document_ref,
                receipt_number=receipt_number,
                verification_status=verification_status,
                issued_at=issued_at,
            )
            db.commit()
            db.refresh(receipt)
            return receipt

    def sign_in(user_id: str = "user-1") -> None:
        token, _ = session_manager.issue(user_id=user_id)
        client.cookies.set(session_manager.settings.session_cookie_name, token)

    return SimpleNamespace(
        client=client,
        lookup=lookup,
        add_receipt=add_receipt,
        sign_in=sign_in,
        db_session_factory=db_session_factory,
    )


# --- capture ---------------------------------------------------------------


def test_capture_stores_and_links_the_receipt(receipts) -> None:
    payment = _payment()
    receipt = receipts.add_receipt(payment=payment)

    assert receipt.payment_id == payment.payment_id
    assert receipt.user_id == "user-1"
    assert receipt.verification_status == "verified"


def test_capture_is_idempotent_per_payment_and_kind(receipts) -> None:
    payment = _payment()
    first = receipts.add_receipt(payment=payment)
    second = receipts.add_receipt(payment=payment)

    assert first.id == second.id


def test_capture_keeps_distinct_kinds_for_one_payment(receipts) -> None:
    payment = _payment()
    official = receipts.add_receipt(payment=payment, kind="official_e_receipt")
    token = receipts.add_receipt(
        payment=payment, kind="token", document_ref="", receipt_number=None
    )

    assert official.id != token.id


# --- list (C-023) ----------------------------------------------------------


def test_list_requires_a_session(receipts) -> None:
    response = receipts.client.get("/v1/receipts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_list_returns_summaries_newest_first(receipts) -> None:
    older = _payment(created_at=FIXED_NOW - timedelta(days=2))
    newer = _payment(created_at=FIXED_NOW, reference="TRX-REF-002")
    receipts.add_receipt(payment=older)
    receipts.add_receipt(payment=newer)
    receipts.sign_in()

    response = receipts.client.get("/v1/receipts")

    assert response.status_code == 200
    body = response.json()
    assert [r["paymentId"] for r in body["receipts"]] == [newer.payment_id, older.payment_id]
    assert body["nextCursor"] is None
    summary = body["receipts"][0]
    assert summary["reference"] == "TRX-REF-002"
    assert summary["payee"] == "Onitsha South LGA"
    assert summary["amount"] == 25_000
    assert summary["currency"] == "NGN"
    assert summary["kind"] == "official_e_receipt"
    assert summary["status"] == "verified"
    assert summary["issuedAt"].endswith("Z")


def test_list_is_empty_without_receipts(receipts) -> None:
    receipts.sign_in()
    response = receipts.client.get("/v1/receipts")
    assert response.json() == {"receipts": [], "nextCursor": None}


def test_list_only_returns_the_owners_receipts(receipts) -> None:
    mine = _payment(user_id="user-1")
    theirs = _payment(user_id="user-2")
    receipts.add_receipt(payment=mine, user_id="user-1")
    receipts.add_receipt(payment=theirs, user_id="user-2")
    receipts.sign_in("user-1")

    response = receipts.client.get("/v1/receipts")

    assert [r["paymentId"] for r in response.json()["receipts"]] == [mine.payment_id]


def test_list_falls_back_to_the_payment_id_when_the_rail_has_not_answered(receipts) -> None:
    payment = _payment(reference=None)
    receipts.add_receipt(payment=payment, receipt_number=None)
    receipts.sign_in()

    response = receipts.client.get("/v1/receipts")

    assert response.json()["receipts"][0]["reference"] == payment.payment_id


def test_list_search_by_reference(receipts) -> None:
    first = _payment(reference="TRX-AAA")
    second = _payment(reference="TRX-BBB", created_at=FIXED_NOW - timedelta(days=1))
    receipts.add_receipt(payment=first)
    receipts.add_receipt(payment=second)
    receipts.sign_in()

    response = receipts.client.get("/v1/receipts", params={"q": "trx-bbb"})

    assert [r["paymentId"] for r in response.json()["receipts"]] == [second.payment_id]


def test_list_search_by_agency(receipts) -> None:
    first = _payment(payee="Onitsha South LGA")
    second = _payment(payee="MTN Nigeria", created_at=FIXED_NOW - timedelta(days=1))
    receipts.add_receipt(payment=first)
    receipts.add_receipt(payment=second)
    receipts.sign_in()

    response = receipts.client.get("/v1/receipts", params={"q": "mtn"})

    assert [r["paymentId"] for r in response.json()["receipts"]] == [second.payment_id]


def test_list_search_by_date(receipts) -> None:
    day = datetime(2026, 2, 14, 10, 0, tzinfo=UTC)
    matching = _payment(created_at=day)
    other = _payment(created_at=FIXED_NOW)
    receipts.add_receipt(payment=matching, issued_at=day)
    receipts.add_receipt(payment=other)
    receipts.sign_in()

    response = receipts.client.get("/v1/receipts", params={"q": "2026-02-14"})

    assert [r["paymentId"] for r in response.json()["receipts"]] == [matching.payment_id]


def test_list_search_with_no_match_is_empty(receipts) -> None:
    receipts.add_receipt(payment=_payment())
    receipts.sign_in()

    response = receipts.client.get("/v1/receipts", params={"q": "nothing matches"})

    assert response.json() == {"receipts": [], "nextCursor": None}


def test_list_paginates_with_an_opaque_cursor(receipts) -> None:
    for index in range(3):
        receipts.add_receipt(payment=_payment(created_at=FIXED_NOW - timedelta(days=index)))
    receipts.sign_in()

    first = receipts.client.get("/v1/receipts", params={"limit": 2})
    cursor = first.json()["nextCursor"]
    assert cursor and len(first.json()["receipts"]) == 2

    second = receipts.client.get("/v1/receipts", params={"limit": 2, "cursor": cursor})

    assert len(second.json()["receipts"]) == 1
    assert second.json()["nextCursor"] is None
    first_ids = {r["paymentId"] for r in first.json()["receipts"]}
    assert not first_ids & {r["paymentId"] for r in second.json()["receipts"]}


def test_list_rejects_a_malformed_cursor(receipts) -> None:
    receipts.sign_in()
    response = receipts.client.get("/v1/receipts", params={"cursor": "not-a-cursor"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_list_is_rate_limited(receipts) -> None:
    receipts.sign_in()
    receipts.client.get("/v1/receipts")
    receipts.client.get("/v1/receipts")

    response = receipts.client.get("/v1/receipts")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


# --- detail (C-024) --------------------------------------------------------


def test_detail_requires_a_session(receipts) -> None:
    receipt = receipts.add_receipt(payment=_payment())
    response = receipts.client.get(f"/v1/receipts/{receipt.id}")
    assert response.status_code == 401


def test_detail_returns_the_receipt_and_its_payment(receipts) -> None:
    payment = _payment()
    receipt = receipts.add_receipt(payment=payment)
    receipts.sign_in()

    response = receipts.client.get(f"/v1/receipts/{receipt.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["receipt"]["id"] == receipt.id
    assert body["receipt"]["paymentId"] == payment.payment_id
    assert body["receipt"]["receiptNumber"] == "FTeR-2026-0001"
    assert body["receipt"]["verificationStatus"] == "verified"
    assert body["receipt"]["documentRef"] == "https://store.example/receipts/abc.pdf"
    assert body["payment"]["paymentId"] == payment.payment_id
    assert body["payment"]["payee"] == "Onitsha South LGA"
    assert body["payment"]["amount"] == 25_000
    assert body["payment"]["status"] == "succeeded"


def test_detail_unknown_receipt_is_404(receipts) -> None:
    receipts.sign_in()
    response = receipts.client.get("/v1/receipts/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_detail_of_another_users_receipt_is_404(receipts) -> None:
    receipt = receipts.add_receipt(payment=_payment(user_id="user-2"), user_id="user-2")
    receipts.sign_in("user-1")

    response = receipts.client.get(f"/v1/receipts/{receipt.id}")

    assert response.status_code == 404


# --- document (C-025) ------------------------------------------------------


def test_document_requires_a_session(receipts) -> None:
    receipt = receipts.add_receipt(payment=_payment())
    response = receipts.client.get(f"/v1/receipts/{receipt.id}/document")
    assert response.status_code == 401


def test_document_returns_the_stored_reference(receipts) -> None:
    receipt = receipts.add_receipt(payment=_payment())
    receipts.sign_in()

    response = receipts.client.get(f"/v1/receipts/{receipt.id}/document")

    assert response.status_code == 200
    body = response.json()
    assert body["documentRef"] == "https://store.example/receipts/abc.pdf"
    assert body["contentType"] == "application/pdf"
    assert body["shareToken"] is None


def test_document_content_type_for_a_token_is_text(receipts) -> None:
    receipt = receipts.add_receipt(payment=_payment(), kind="token", document_ref="token:abc123")
    receipts.sign_in()

    response = receipts.client.get(f"/v1/receipts/{receipt.id}/document")

    assert response.json()["contentType"] == "text/plain"


def test_document_awaiting_the_source_is_409(receipts) -> None:
    receipt = receipts.add_receipt(payment=_payment(), document_ref="", receipt_number=None)
    receipts.sign_in()

    response = receipts.client.get(f"/v1/receipts/{receipt.id}/document")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_document_unknown_receipt_is_404(receipts) -> None:
    receipts.sign_in()
    response = receipts.client.get("/v1/receipts/does-not-exist/document")
    assert response.status_code == 404


# --- store boundary --------------------------------------------------------


def test_list_reports_payment_unavailable_when_the_store_is_not_wired(
    app, client, session_manager, db_session_factory
) -> None:
    app.state.session_factory = db_session_factory
    # No lookup bound: the default refuses rather than fabricating fields.
    if not _mounted(app):
        app.include_router(receipts_router, prefix="/v1")
    # Seed a receipt directly so the list has a payment to resolve.
    with db_session_factory() as db:
        service.capture_receipt(
            db,
            payment_id=new_id(),
            user_id="user-1",
            kind="official_e_receipt",
            document_ref="https://store.example/receipts/abc.pdf",
        )
        db.commit()
    token, _ = session_manager.issue(user_id="user-1")
    client.cookies.set(session_manager.settings.session_cookie_name, token)

    response = client.get("/v1/receipts")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "payment_unavailable"


def test_list_without_receipts_does_not_need_the_payment_store(
    app, client, session_manager, db_session_factory
) -> None:
    app.state.session_factory = db_session_factory
    if not _mounted(app):
        app.include_router(receipts_router, prefix="/v1")
    token, _ = session_manager.issue(user_id="user-1")
    client.cookies.set(session_manager.settings.session_cookie_name, token)

    response = client.get("/v1/receipts")

    assert response.status_code == 200
    assert response.json() == {"receipts": [], "nextCursor": None}
