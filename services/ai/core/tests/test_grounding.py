from __future__ import annotations

from core.grounding import (
    amount_is_traceable,
    amounts_in_text,
    build_context,
    ground_intent,
    ground_ranking,
)
from core.retrieval import RetrievedRecord
from core.schemas import Intent, RankingResult, ServiceSummary


def _context():
    record = RetrievedRecord.from_service(
        {
            "service_id": "svc-landuse",
            "name": "Land Use Charge",
            "collecting_body": "Lagos State Government",
            "category": "government",
            "known_amount": 2500000,
            "currency": "NGN",
            "reference": "LUC-2026-0001",
        }
    )
    return build_context([record])


def test_amounts_in_text_reads_digits_commas_and_suffixes():
    found = amounts_in_text("I want to pay 5,000 naira and 2k more")
    assert 5000 in found
    assert 2000 in found


def test_amounts_in_text_reads_number_words():
    assert 5000 in amounts_in_text("buy five thousand MTN")


def test_amount_is_traceable_accepts_naira_to_kobo_conversion():
    context = _context()
    assert amount_is_traceable(500000, user_text="pay five thousand", context=context)
    assert amount_is_traceable(2500000, user_text="land use", context=context)


def test_amount_is_not_traceable_when_invented():
    context = _context()
    assert not amount_is_traceable(999, user_text="pay my bill", context=context)


def test_ground_intent_drops_an_ungrounded_target_and_collapses_payment():
    context = _context()
    intent = Intent(
        intent_type="bill_payment",
        confidence=0.95,
        target="svc-invented",
        amount=None,
    )
    grounded, report = ground_intent(intent, user_text="pay my bill", context=context)
    assert grounded.target is None
    assert grounded.intent_type == "unknown"
    assert {"ungrounded_target", "unresolved"} <= report.flags


def test_ground_intent_keeps_a_grounded_target():
    context = _context()
    intent = Intent(
        intent_type="gov_payment",
        confidence=0.95,
        target="svc-landuse",
        reference="LUC-2026-0001",
    )
    grounded, report = ground_intent(intent, user_text="pay land use charge", context=context)
    assert grounded.target == "svc-landuse"
    assert grounded.intent_type == "gov_payment"
    assert report.flags == frozenset()
    assert report.citations == ("svc-landuse",)


def test_ground_intent_drops_an_invented_reference():
    context = _context()
    intent = Intent(
        intent_type="receipt_lookup",
        confidence=0.9,
        reference="FAKE-REF",
    )
    grounded, report = ground_intent(intent, user_text="find my receipt", context=context)
    assert grounded.reference is None
    assert "ungrounded_reference" in report.flags


def test_ground_ranking_filters_an_invented_service():
    context = _context()
    invented = ServiceSummary(
        service_id="svc-fake",
        name="Fake",
        collecting_body="Fake Body",
        category="other",
        confidence=0.99,
    )
    result = ground_ranking(RankingResult(results=(invented,)), context=context)
    assert result.results == ()
    assert result.no_match is True


def test_ground_ranking_keeps_known_services_in_order():
    context = _context()
    known = ServiceSummary(
        service_id="svc-landuse",
        name="Land Use Charge",
        collecting_body="Lagos State Government",
        category="government",
        confidence=0.9,
    )
    result = ground_ranking(RankingResult(results=(known,), no_match=False), context=context)
    assert [item.service_id for item in result.results] == ["svc-landuse"]
