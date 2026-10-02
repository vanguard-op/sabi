"""Shared fixtures for the model-serving unit tests.

The model is mocked or recorded in every test; nothing here makes a network call or
requires the google-genai SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``services/ai`` importable as the package root when pytest is invoked from
# either the repository root or the service directory.
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

from core.testing import FakeCandidate, index_over  # noqa: E402


@pytest.fixture
def candidates() -> list[FakeCandidate]:
    return [
        FakeCandidate(
            service_id="svc-electric",
            name="Ikeja Electric",
            collecting_body="Ikeja Electricity Distribution Company",
            category="electricity",
            known_amount=1200000,
            aliases=("electricity", "power", "light"),
        ),
        FakeCandidate(
            service_id="svc-water",
            name="Lagos Water",
            collecting_body="Lagos Water Corporation",
            category="water",
            aliases=("water",),
        ),
        FakeCandidate(
            service_id="svc-landuse",
            name="Land Use Charge",
            collecting_body="Lagos State Government",
            category="government",
            known_amount=2500000,
            aliases=("land use", "levy", "land"),
        ),
    ]


@pytest.fixture
def catalogue(candidates):
    return index_over(candidates)


@pytest.fixture
def lookup(candidates):
    return {candidate.service_id: candidate for candidate in candidates}
