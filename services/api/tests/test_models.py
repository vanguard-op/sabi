from sqlalchemy import Integer

from app.core.privacy import PERSONAL_DATA_FIELDS
from app.db import models  # noqa: F401  (registers metadata)
from app.db.base import Base

# schema.md entity -> primary-store table.
ENTITY_TABLES = {
    "User": "users",
    "AuthCredential": "auth_credentials",
    "ChannelLink": "channel_links",
    "IdentityVerification": "identity_verifications",
    "Service": "services",
    "Provider": "providers",
    "Capability": "capabilities",
    "Receipt": "receipts",
    "PaymentCase": "payment_cases",
    "Reminder": "reminders",
    "Pool": "pools",
    "Contribution": "contributions",
    "Notification": "notifications",
}


def _camel_to_snake(name: str) -> str:
    return "".join(f"_{char.lower()}" if char.isupper() else char for char in name)


def test_every_schema_entity_has_a_table() -> None:
    tables = Base.metadata.tables
    for entity, table in ENTITY_TABLES.items():
        assert table in tables, f"{entity} is missing table {table}"


def test_personal_data_fields_are_marked_on_columns() -> None:
    for entity, fields in PERSONAL_DATA_FIELDS.items():
        if entity not in ENTITY_TABLES:  # PaymentMethod lives in the payment store
            continue
        table = Base.metadata.tables[ENTITY_TABLES[entity]]
        for field in fields:
            column = table.columns[_camel_to_snake(field)]
            assert column.info.get("personal_data") is True, f"{entity}.{field}"


def test_amounts_are_integer_minor_units_paired_with_currency() -> None:
    for table_name, amount_column, currency_column in (
        ("services", "known_amount", "currency"),
        ("capabilities", "price_amount", "price_currency"),
        ("pools", "target_amount", "currency"),
        ("contributions", "amount", "currency"),
    ):
        table = Base.metadata.tables[table_name]
        assert isinstance(table.columns[amount_column].type, Integer)
        assert currency_column in table.columns


def test_no_full_card_or_account_number_column_exists() -> None:
    forbidden = ("card_number", "account_number", "full_pan", "pan_number")
    for table in Base.metadata.tables.values():
        assert not set(forbidden) & set(table.columns.keys()), table.name


def test_channel_link_is_unique_per_address() -> None:
    table = Base.metadata.tables["channel_links"]
    unique_column_sets = {
        tuple(sorted(constraint.columns.keys()))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("address", "channel") in unique_column_sets
