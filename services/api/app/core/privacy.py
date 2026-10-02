"""Privacy policy: data classes, retention, residency, and personal-data fields.

NFR-040 (NDPA 2023) requires a lawful basis, consent, access, and deletion, with
a documented data lifecycle. This module holds that lifecycle as data so
retention and erasure can be enforced in one place, and names every field the
schema annotates ``x-personal-data``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

# Residency for every class: Nigeria (nfr.md, data lifecycle).
RESIDENCY = "NG"

SEVEN_YEARS_DAYS = 365 * 7
TWENTY_FOUR_MONTHS_DAYS = 730


class DataClass(StrEnum):
    ACCOUNT_PROFILE = "account_profile"
    PAYMENT_RECEIPT = "payment_receipt"
    IDENTITY_VERIFICATION = "identity_verification"
    USAGE_ANALYTICS = "usage_analytics"
    SUPPORT_CASES = "support_cases"


@dataclass(frozen=True, slots=True)
class LifecycleRule:
    retention_days: int | None
    statutory_hold: bool
    deletion: str


LIFECYCLE: dict[DataClass, LifecycleRule] = {
    DataClass.ACCOUNT_PROFILE: LifecycleRule(
        retention_days=30,
        statutory_hold=False,
        deletion="hard-delete within 30 days of a valid request",
    ),
    DataClass.PAYMENT_RECEIPT: LifecycleRule(
        retention_days=SEVEN_YEARS_DAYS,
        statutory_hold=True,
        deletion="retained by law, access-restricted, never sold",
    ),
    DataClass.IDENTITY_VERIFICATION: LifecycleRule(
        retention_days=None,
        statutory_hold=True,
        deletion="deleted when the KYC retention obligation ends",
    ),
    DataClass.USAGE_ANALYTICS: LifecycleRule(
        retention_days=TWENTY_FOUR_MONTHS_DAYS,
        statutory_hold=False,
        deletion="aggregated and anonymised on expiry",
    ),
    DataClass.SUPPORT_CASES: LifecycleRule(
        retention_days=TWENTY_FOUR_MONTHS_DAYS,
        statutory_hold=False,
        deletion="deleted on request where no statutory hold applies",
    ),
}

# Fields annotated x-personal-data in schema.md, mapped to the class that owns
# their retention. Entity names match the schema titles.
PERSONAL_DATA_FIELDS: dict[str, frozenset[str]] = {
    "User": frozenset({"displayName"}),
    "AuthCredential": frozenset({"publicKey", "secretHash"}),
    "ChannelLink": frozenset({"address"}),
    "IdentityVerification": frozenset({"identifierMasked"}),
    "PaymentMethod": frozenset({"maskedIdentifier", "processorToken"}),
    "Provider": frozenset({"contactEmail"}),
}

PERSONAL_DATA_CLASS: dict[str, DataClass] = {
    "User": DataClass.ACCOUNT_PROFILE,
    "AuthCredential": DataClass.ACCOUNT_PROFILE,
    "ChannelLink": DataClass.ACCOUNT_PROFILE,
    "IdentityVerification": DataClass.IDENTITY_VERIFICATION,
    "PaymentMethod": DataClass.PAYMENT_RECEIPT,
    "Provider": DataClass.SUPPORT_CASES,
}


def is_personal_data(entity: str, field_name: str) -> bool:
    return field_name in PERSONAL_DATA_FIELDS.get(entity, frozenset())


def deletion_due_at(data_class: DataClass, created_at: datetime) -> datetime | None:
    """When a record becomes eligible for deletion, or None under statutory hold."""
    rule = LIFECYCLE[data_class]
    if rule.retention_days is None:
        return None
    return created_at + timedelta(days=rule.retention_days)
