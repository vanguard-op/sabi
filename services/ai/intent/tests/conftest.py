"""Deterministic fixtures for intent resolution tests.

The model is mocked or recorded in every test; nothing here touches the network or
the google-genai SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``services/ai`` importable when pytest is invoked from the service root or
# from within this package directory.
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

from core.retrieval import KeywordRetrievalIndex, RetrievedRecord  # noqa: E402


def _record(
    service_id: str,
    name: str,
    collecting_body: str,
    category: str,
    known_amount: int | None = None,
    aliases: tuple[str, ...] = (),
) -> RetrievedRecord:
    fields: dict[str, object] = {
        "service_id": service_id,
        "name": name,
        "collecting_body": collecting_body,
        "category": category,
        "known_amount": known_amount,
        "currency": "NGN",
        "status": "active",
    }
    if aliases:
        fields["aliases"] = list(aliases)
    return RetrievedRecord.from_service(fields)


@pytest.fixture
def records() -> list[RetrievedRecord]:
    return [
        _record(
            "svc-electric",
            "Ikeja Electric",
            "Ikeja Electricity Distribution Company",
            "electricity",
            known_amount=1200000,
            aliases=("electricity", "power", "light"),
        ),
        _record(
            "svc-landuse",
            "Land Use Charge",
            "Lagos State Government",
            "government",
            known_amount=2500000,
            aliases=("land use", "levy"),
        ),
    ]


@pytest.fixture
def catalogue(records: list[RetrievedRecord]) -> KeywordRetrievalIndex:
    return KeywordRetrievalIndex(records)
