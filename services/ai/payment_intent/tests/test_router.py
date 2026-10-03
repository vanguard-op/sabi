"""Unit tests for the payment-intent HTTP adapter.

The model is a deterministic double and the router is mounted on a throwaway app with
the shared validation handler, so the suite exercises the handler, the wire shape, and
the error envelope without depending on service-level wiring.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from core.errors import ProviderUnavailable
from core.testing import FakeModelProvider, json_response
from payment_intent.deps import get_payment_intent_service
from payment_intent.errors import validation_error_handler
from payment_intent.router import router
from payment_intent.service import PaymentIntentService

PATH = "/v1/agent/payment-intents"


def _extraction(**overrides):
    payload = {
        "service_id": "svc-landuse",
        "amount": 500000,
        "currency": "NGN",
        "payee_reference": None,
        "confidence": 0.93,
        "language": "en",
        "clarifying_question": None,
    }
    payload.update(overrides)
    return payload


def _service(catalogue, responses=None) -> PaymentIntentService:
    return PaymentIntentService(FakeModelProvider(responses), catalogue)


@contextmanager
def _client(service: PaymentIntentService) -> Iterator[TestClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_payment_intent_service] = lambda: service
    with TestClient(app) as client:
        yield client


def test_extraction_returns_the_camel_case_body(catalogue):
    with _client(_service(catalogue, [json_response(_extraction())])) as client:
        response = client.post(PATH, json={"text": "pay my land use charge 5000"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"paymentIntent", "candidates", "source"}
    assert body["source"] == "model"
    assert set(body["paymentIntent"]) == {
        "serviceId",
        "payee",
        "amount",
        "currency",
        "payeeReference",
        "intentType",
        "confidence",
        "language",
        "clarifyingQuestion",
        "resolved",
    }
    assert body["paymentIntent"]["serviceId"] == "svc-landuse"
    assert body["paymentIntent"]["payee"] == "Lagos State Government"
    assert body["paymentIntent"]["amount"] == 500000
    assert body["paymentIntent"]["resolved"] is True
    assert [c["serviceId"] for c in body["candidates"]] == ["svc-landuse"]


def test_provider_failure_still_answers_200_with_the_fallback(catalogue):
    with _client(_service(catalogue, [ProviderUnavailable("down")])) as client:
        response = client.post(PATH, json={"text": "pay my electricity"})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert body["paymentIntent"]["resolved"] is False
    assert body["paymentIntent"]["clarifyingQuestion"]
    assert [c["serviceId"] for c in body["candidates"]] == ["svc-electric"]


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "   "},
        {"text": "x" * 201},
        {"text": "pay electricity", "locale": "fr"},
        {"text": "pay electricity", "channel": "carrier-pigeon"},
    ],
)
def test_invalid_input_is_a_400_envelope(catalogue, payload):
    with _client(_service(catalogue, [json_response(_extraction())])) as client:
        response = client.post(PATH, json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_missing_body_field_maps_to_the_400_envelope(catalogue):
    with _client(_service(catalogue, [json_response(_extraction())])) as client:
        response = client.post(PATH, json={"locale": "en"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
