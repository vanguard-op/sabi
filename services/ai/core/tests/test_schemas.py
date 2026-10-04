from __future__ import annotations

import pytest

from core.errors import OutputValidationError
from core.schemas import Intent, IntentModelOutput, RankingResult, ServiceSummary


def _intent_payload(**overrides):
    payload = {
        "reply": "I've got Ikeja Electric. Tell me the amount and I'll get it ready.",
        "intent_type": "bill_payment",
        "target": "svc-electric",
        "amount": 500000,
        "currency": "NGN",
        "reference": None,
        "constraints": {},
        "confidence": 0.95,
        "detected_language": None,
    }
    payload.update(overrides)
    return payload


def test_intent_parses_a_valid_payload():
    intent = Intent.from_mapping(_intent_payload())
    assert intent.intent_type == "bill_payment"
    assert intent.amount == 500000
    assert intent.currency == "NGN"


def test_intent_rejects_unknown_type():
    with pytest.raises(OutputValidationError):
        Intent.from_mapping(_intent_payload(intent_type="send_money"))


def test_intent_rejects_boolean_amount():
    with pytest.raises(OutputValidationError):
        Intent.from_mapping(_intent_payload(amount=True))


def test_intent_rejects_negative_amount():
    with pytest.raises(OutputValidationError):
        Intent.from_mapping(_intent_payload(amount=-1))


@pytest.mark.parametrize("confidence", [-0.1, 1.1, "high"])
def test_intent_rejects_out_of_range_confidence(confidence):
    with pytest.raises(OutputValidationError):
        Intent.from_mapping(_intent_payload(confidence=confidence))


def test_intent_rejects_unknown_detected_language():
    with pytest.raises(OutputValidationError):
        Intent.from_mapping(_intent_payload(detected_language="fr"))


def test_intent_defaults_currency_and_allows_nulls():
    intent = Intent.from_mapping({"intent_type": "unknown", "confidence": 0.1})
    assert intent.currency == "NGN"
    assert intent.target is None
    assert intent.amount is None
    assert intent.constraints == {}


def test_intent_round_trips_to_the_contract_shape():
    mapping = Intent.from_mapping(_intent_payload()).to_mapping()
    assert mapping["intent_type"] == "bill_payment"
    assert mapping["amount"] == 500000


def test_intent_carries_only_machine_actionable_fields():
    mapping = Intent.from_mapping(_intent_payload()).to_mapping()
    # The reply and the greeting/clarifying question are not part of the structured
    # intent; ``language`` and ``clarifying_question`` are gone (C-009 revision 4).
    assert set(mapping) == {
        "intent_type",
        "target",
        "amount",
        "currency",
        "reference",
        "constraints",
        "confidence",
        "detected_language",
    }


def test_intent_output_parses_the_reply_alongside_the_intent():
    output = IntentModelOutput.from_mapping(_intent_payload())
    assert output.reply.startswith("I've got Ikeja Electric")
    assert output.intent.intent_type == "bill_payment"
    assert output.intent.detected_language is None


def test_intent_output_allows_a_null_reply():
    output = IntentModelOutput.from_mapping(_intent_payload(reply=None))
    assert output.reply is None
    # An empty reply is treated exactly like a missing one, never a blank turn.
    output = IntentModelOutput.from_mapping(_intent_payload(reply="   "))
    assert output.reply is None


def _service(**overrides):
    payload = {
        "service_id": "svc-electric",
        "name": "Ikeja Electric",
        "collecting_body": "Ikeja Electricity Distribution Company",
        "category": "electricity",
        "known_amount": 1200000,
        "currency": "NGN",
        "status": "active",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def test_service_summary_parses_and_exposes_contract_fields():
    summary = ServiceSummary.from_mapping(_service())
    assert summary.service_id == "svc-electric"
    assert summary.known_amount == 1200000
    assert summary.to_mapping()["collecting_body"].startswith("Ikeja")


def test_service_summary_requires_identifiers():
    with pytest.raises(OutputValidationError):
        ServiceSummary.from_mapping(_service(name=""))


def test_ranking_parses_and_infers_no_match():
    result = RankingResult.from_mapping({"results": [], "no_match": True})
    assert result.no_match is True
    assert result.results == ()


def test_ranking_rejects_more_than_five_results():
    items = [_service(service_id=f"svc-{i}") for i in range(6)]
    with pytest.raises(OutputValidationError):
        RankingResult.from_mapping({"results": items, "no_match": False})


def test_ranking_rejects_empty_results_without_no_match():
    with pytest.raises(OutputValidationError):
        RankingResult.from_mapping({"results": [], "no_match": False})
