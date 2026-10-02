from fastapi.testclient import TestClient

from sabi_payments.core.config import PaymentSettings
from sabi_payments.db.base import Base
from sabi_payments.main import create_app

ENTITY_TABLES = {
    "PaymentMandate": "payment_mandates",
    "PaymentMethod": "payment_methods",
    "Payment": "payments",
    "PaymentEvent": "payment_events",
}


def test_payment_entities_have_tables() -> None:
    tables = Base.metadata.tables
    for entity, table in ENTITY_TABLES.items():
        assert table in tables, f"{entity} is missing table {table}"


def test_idempotency_key_is_unique() -> None:
    payments = Base.metadata.tables["payments"]
    unique_columns = {
        tuple(sorted(constraint.columns.keys()))
        for constraint in payments.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("idempotency_key",) in unique_columns


def test_payment_store_has_no_foreign_keys_into_the_primary_store() -> None:
    allowed_targets = {"payment_mandates", "payment_methods", "payments"}
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.column.table.name in allowed_targets, table.name


def test_payment_method_stores_only_a_masked_identifier() -> None:
    table = Base.metadata.tables["payment_methods"]
    assert table.columns["masked_identifier"].info.get("personal_data") is True
    assert table.columns["processor_token"].info.get("personal_data") is True
    assert not {"card_number", "account_number"} & set(table.columns.keys())


def test_payment_snapshots_amount_and_payee() -> None:
    table = Base.metadata.tables["payments"]
    for column in ("amount", "currency", "payee"):
        assert table.columns[column].nullable is False


def test_payment_app_health() -> None:
    settings = PaymentSettings(
        _env_file=None,
        payments_database_url="postgresql+psycopg://sabi:secret@localhost:5432/sabi_payments",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json() == {"status": "ok"}
