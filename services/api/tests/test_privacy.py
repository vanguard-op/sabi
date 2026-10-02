from datetime import timedelta

from app.core.privacy import (
    LIFECYCLE,
    PERSONAL_DATA_FIELDS,
    RESIDENCY,
    DataClass,
    deletion_due_at,
    is_personal_data,
)
from app.core.time import utcnow

# The exact set annotated x-personal-data in schema.md.
SCHEMA_PERSONAL_DATA = {
    "User": {"displayName"},
    "AuthCredential": {"publicKey", "secretHash"},
    "ChannelLink": {"address"},
    "IdentityVerification": {"identifierMasked"},
    "PaymentMethod": {"maskedIdentifier", "processorToken"},
    "Provider": {"contactEmail"},
}


def test_personal_data_registry_matches_the_schema() -> None:
    assert {entity: set(fields) for entity, fields in PERSONAL_DATA_FIELDS.items()} == (
        SCHEMA_PERSONAL_DATA
    )
    assert is_personal_data("User", "displayName") is True
    assert is_personal_data("User", "locale") is False


def test_residency_is_nigeria_for_every_class() -> None:
    assert RESIDENCY == "NG"
    for rule in LIFECYCLE.values():
        assert rule.retention_days is None or rule.retention_days > 0


def test_account_profile_deletion_due_after_thirty_days() -> None:
    created = utcnow()
    due = deletion_due_at(DataClass.ACCOUNT_PROFILE, created)
    assert due == created + timedelta(days=30)


def test_statutory_classes_are_retained() -> None:
    created = utcnow()
    assert deletion_due_at(DataClass.PAYMENT_RECEIPT, created) is not None
    assert deletion_due_at(DataClass.IDENTITY_VERIFICATION, created) is None
    assert LIFECYCLE[DataClass.PAYMENT_RECEIPT].statutory_hold is True
