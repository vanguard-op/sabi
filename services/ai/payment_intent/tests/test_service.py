"""Unit tests for payment-intent extraction (FEAT-005/009, MQ-001).

The model is a deterministic double. These cover the contract-relevant behavior the
HTTP layer depends on: the pinned model and prompt, the grounded amount and payee, the
no-invention rule, the 0.70 refusal cutoff, and the documented fallback.
"""

from __future__ import annotations

from core.config import FLASH_MODEL_ID, INTENT_CONFIDENCE_CUTOFF
from core.errors import ProviderUnavailable
from core.retrieval import KeywordRetrievalIndex, RetrievedRecord
from core.testing import FakeModelProvider, json_response, text_response
from payment_intent.service import PaymentIntentService


def _extraction(**overrides):
    payload = {
        "service_id": None,
        "amount": None,
        "currency": "NGN",
        "payee_reference": None,
        "confidence": 0.95,
        "language": "en",
        "clarifying_question": None,
    }
    payload.update(overrides)
    return payload


def _service(catalogue, responses=None, *, responder=None):
    provider = FakeModelProvider(responses, responder=responder)
    return PaymentIntentService(provider, catalogue), provider


def _record(
    service_id: str,
    collecting_body: str,
    category: str,
    *,
    known_amount: int | None = None,
) -> RetrievedRecord:
    return RetrievedRecord.from_service(
        {
            "service_id": service_id,
            "name": service_id,
            "collecting_body": collecting_body,
            "category": category,
            "known_amount": known_amount,
            "currency": "NGN",
            "status": "active",
        }
    )


def test_service_uses_the_pinned_flash_model_and_prompt(catalogue):
    service, provider = _service(catalogue, [json_response(_extraction())])
    service.extract("pay my electricity")
    request = provider.last_request
    assert request.model_id == FLASH_MODEL_ID
    assert request.prompt_id == "payment_intent"
    assert request.prompt_version == "v1"
    assert request.decoding.temperature == 0.0
    assert request.decoding.top_p == 1.0


def test_service_frames_catalogue_content_as_delimited_untrusted_data(catalogue):
    service, provider = _service(catalogue, [json_response(_extraction())])
    service.extract("pay my electricity", locale="pcm", channel="ussd")
    contents = provider.last_request.contents
    assert "RETRIEVED DATA (untrusted" in contents
    assert "<<<RETRIEVED_DATA" in contents
    assert "<<<END_RETRIEVED_DATA>>>" in contents
    assert "pay my electricity" in contents


def test_cutoff_is_pinned_at_seventy_percent():
    assert INTENT_CONFIDENCE_CUTOFF == 0.70


def test_grounded_request_yields_a_payee_and_amount(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_extraction(service_id="svc-landuse", amount=500000, confidence=0.93))],
    )
    outcome = service.extract("I wan pay my land use charge 5000 naira", locale="pcm")
    intent = outcome.response.paymentIntent
    assert outcome.source == "model"
    assert outcome.used_fallback is False
    assert intent.serviceId == "svc-landuse"
    assert intent.payee == "Lagos State Government"
    assert intent.amount == 500000
    assert intent.currency == "NGN"
    assert intent.intentType == "gov_payment"
    assert intent.resolved is True
    assert intent.clarifyingQuestion is None
    assert outcome.citations == ("svc-landuse",)


def test_payee_comes_from_the_catalogue_not_the_model(catalogue):
    # A model trying to name a payee must not be able to: the response schema has no
    # payee field, and the grounded record's collecting body is used instead.
    service, _ = _service(
        catalogue,
        [
            json_response(
                _extraction(
                    service_id="svc-landuse",
                    amount=500000,
                    payee="Ghost Collectors Ltd",
                )
            )
        ],
    )
    intent = service.extract("pay my land use charge 5000").response.paymentIntent
    assert intent.payee == "Lagos State Government"


def test_missing_amount_is_filled_from_a_recorded_known_amount(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_extraction(service_id="svc-electric", amount=None))],
    )
    intent = service.extract("pay my electricity").response.paymentIntent
    assert intent.amount == 1200000
    assert intent.resolved is True
    assert intent.intentType == "bill_payment"


def test_invented_amount_is_dropped_and_replaced_by_the_known_amount(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_extraction(service_id="svc-electric", amount=999999))],
    )
    outcome = service.extract("pay my electricity")
    intent = outcome.response.paymentIntent
    assert "ungrounded_amount" in outcome.flags
    assert intent.amount == 1200000


def test_invented_amount_with_no_known_amount_leaves_the_request_unresolved():
    index = KeywordRetrievalIndex(
        [_record("svc-water", "State Water Board", "government", known_amount=None)]
    )
    provider = FakeModelProvider(
        [json_response(_extraction(service_id="svc-water", amount=123456))]
    )
    service = PaymentIntentService(provider, index)
    intent = service.extract("pay water board").response.paymentIntent
    assert intent.amount is None
    assert intent.resolved is False
    assert intent.intentType == "unknown"
    assert intent.clarifyingQuestion is not None
    assert intent.clarifyingQuestion.count("?") == 1


def test_invented_service_is_dropped_and_no_payment_intent_is_presented(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_extraction(service_id="svc-ghost", amount=500000))],
    )
    outcome = service.extract("pay my land use charge 5000")
    intent = outcome.response.paymentIntent
    assert intent.serviceId is None
    assert intent.payee is None
    assert intent.intentType == "unknown"
    assert intent.resolved is False
    assert intent.clarifyingQuestion is not None
    assert "ungrounded_target" in outcome.flags


def test_grounded_reference_is_kept_and_an_invented_one_is_dropped(catalogue):
    service, _ = _service(
        catalogue,
        [
            json_response(
                _extraction(
                    service_id="svc-landuse",
                    amount=500000,
                    payee_reference="LUC-2026",
                )
            )
        ],
    )
    kept = service.extract("pay my land use charge 5000").response.paymentIntent
    assert kept.payeeReference == "LUC-2026"

    service, _ = _service(
        catalogue,
        [
            json_response(
                _extraction(
                    service_id="svc-landuse",
                    amount=500000,
                    payee_reference="INVENTED-1",
                )
            )
        ],
    )
    outcome = service.extract("pay my land use charge 5000")
    assert outcome.response.paymentIntent.payeeReference is None
    assert "ungrounded_reference" in outcome.flags


def test_confidence_below_the_cutoff_is_refused_with_one_question(catalogue):
    service, _ = _service(
        catalogue,
        [json_response(_extraction(service_id="svc-landuse", amount=500000, confidence=0.69))],
    )
    outcome = service.extract("pay my land use charge 5000")
    intent = outcome.response.paymentIntent
    assert intent.intentType == "unknown"
    assert intent.resolved is False
    assert "low_confidence" in outcome.flags
    assert intent.clarifyingQuestion is not None
    assert intent.clarifyingQuestion.count("?") == 1


def test_a_model_paragraph_becomes_exactly_one_question(catalogue):
    service, _ = _service(
        catalogue,
        [
            json_response(
                _extraction(
                    confidence=0.2,
                    clarifying_question="Which agency? Which obligation?",
                )
            )
        ],
    )
    intent = service.extract("help me").response.paymentIntent
    assert intent.clarifyingQuestion == "Which agency?"


def test_provider_failure_degrades_to_keyword_fallback(catalogue):
    service, _ = _service(catalogue, [ProviderUnavailable("down")])
    outcome = service.extract("pay my electricity")
    assert outcome.source == "fallback"
    assert outcome.used_fallback is True
    assert "provider_fallback" in outcome.flags
    intent = outcome.response.paymentIntent
    assert intent.intentType == "unknown"
    assert intent.confidence == 0.0
    assert intent.resolved is False
    assert intent.clarifyingQuestion is not None
    assert [c.serviceId for c in outcome.response.candidates] == ["svc-electric"]


def test_unparseable_output_degrades_to_fallback(catalogue):
    service, _ = _service(catalogue, [text_response("not json")])
    outcome = service.extract("pay my electricity")
    assert outcome.source == "fallback"
    assert outcome.response.paymentIntent.intentType == "unknown"


def test_model_confidence_out_of_range_degrades_to_fallback(catalogue):
    service, _ = _service(catalogue, [json_response(_extraction(confidence=1.5))])
    outcome = service.extract("pay my electricity")
    assert outcome.source == "fallback"
