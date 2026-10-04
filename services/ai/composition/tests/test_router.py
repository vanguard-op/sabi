"""Contract conformance for POST /v1/agent/surfaces (C-012, MQ-003).

The model is mocked in every test, so the suite is deterministic and never
touches the network or the google-genai SDK.
"""

from __future__ import annotations

from composition.tests.conftest import build_test_client
from core.config import PRIMARY_MODEL_ID
from core.errors import ProviderUnavailable
from core.schemas import FALLBACK_TASKS
from core.testing import json_response

_HEADERS = {"Content-Type": "application/json"}


def _verification_stream() -> dict:
    return {
        "messages": [
            {"type": "createSurface", "surfaceId": "verify-1", "task": "verification"},
            {
                "type": "updateComponents",
                "components": [
                    {"component": "StatusPill", "id": "status"},
                    {"component": "ConfirmationSummary", "id": "details"},
                ],
            },
            {"type": "updateDataModel", "data": {"status": "unverified"}},
        ]
    }


def _recovery_stream() -> dict:
    return {
        "messages": [
            {"type": "createSurface", "surfaceId": "case-1", "task": "recovery"},
            {
                "type": "updateComponents",
                "components": [
                    {"component": "StatusPill", "id": "status"},
                    {"component": "ConfirmationSummary", "id": "payment"},
                ],
            },
            {"type": "updateDataModel", "data": {"caseReference": "CASE-7", "state": "refunding"}},
        ]
    }


def _record_receipt_stream() -> dict:
    return {
        "messages": [
            {"type": "createSurface", "surfaceId": "receipt-1", "task": "receipt"},
            {
                "type": "updateComponents",
                "components": [{"component": "ReceiptCard", "id": "receipt"}],
            },
            {"type": "updateDataModel", "data": {"receiptId": "rcpt-9", "kind": "token"}},
        ]
    }


def _valid_stream() -> dict:
    return {
        "messages": [
            {"type": "createSurface", "surfaceId": "confirm-1"},
            {
                "type": "updateComponents",
                "components": [{"component": "ConfirmationSummary", "id": "summary"}],
            },
            {"type": "updateDataModel", "data": {"amount": 500000}},
        ]
    }


# --- Happy path ------------------------------------------------------------------


def test_composes_a_catalogue_valid_surface() -> None:
    client, _ = build_test_client([json_response(_valid_stream(), model_id=PRIMARY_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "confirmation", "context": {"amount": 500000, "payee": "Ikeja Electric"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert [message["type"] for message in body["messages"]] == [
        "createSurface",
        "updateComponents",
        "updateDataModel",
    ]
    assert body["fallback"] == "confirmation"


def test_composes_a_verification_surface() -> None:
    client, provider = build_test_client(
        [json_response(_verification_stream(), model_id=PRIMARY_MODEL_ID)]
    )
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "verification", "context": {"status": "unverified"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] == "verification"
    assert body["messages"][0]["task"] == "verification"
    assert "verification" in provider.last_request.contents


def test_composes_a_recovery_surface() -> None:
    client, _ = build_test_client([json_response(_recovery_stream(), model_id=PRIMARY_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "recovery", "context": {"caseReference": "CASE-7"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] == "recovery"
    assert [message["type"] for message in body["messages"]] == [
        "createSurface",
        "updateComponents",
        "updateDataModel",
    ]


def test_receipt_accepts_a_resolved_record_context() -> None:
    """A `receipt` task composes a resolved record, not only a post-payment payment.

    The context carries a record reference from a record lookup; the resolved record's
    own fields reach the prompt unmodified (FEAT-011, MQ-003 contract impact).
    """

    client, provider = build_test_client(
        [json_response(_record_receipt_stream(), model_id=PRIMARY_MODEL_ID)]
    )
    context = {"recordKind": "receipt", "reference": "FT-2026-1", "receiptId": "rcpt-9"}
    response = client.post("/v1/agent/surfaces", json={"task": "receipt", "context": context})
    assert response.status_code == 200
    assert response.json()["fallback"] == "receipt"
    request_contents = provider.last_request.contents
    assert "FT-2026-1" in request_contents
    assert "rcpt-9" in request_contents


def test_every_contract_task_is_accepted() -> None:
    """Every C-012 task (including verification and recovery) is a known task."""

    assert FALLBACK_TASKS == {
        "confirmation",
        "amount_entry",
        "receipt",
        "discovery",
        "verification",
        "recovery",
    }
    for task in sorted(FALLBACK_TASKS):
        client, _ = build_test_client([json_response(_valid_stream(), model_id=PRIMARY_MODEL_ID)])
        response = client.post("/v1/agent/surfaces", json={"task": task, "context": {}})
        assert response.status_code == 200, task
        assert response.json()["fallback"] == task


def test_invalid_composition_keeps_the_new_task_fallback() -> None:
    payload = {
        "messages": [
            {"type": "updateComponents", "components": [{"component": "EvilWidget", "id": "x"}]}
        ]
    }
    client, _ = build_test_client([json_response(payload, model_id=PRIMARY_MODEL_ID)])
    for task in ("verification", "recovery"):
        response = client.post("/v1/agent/surfaces", json={"task": task, "context": {}})
        assert response.status_code == 200
        assert response.json() == {"messages": [], "fallback": task}


def test_composition_runs_on_the_pinned_primary_model_and_prompt() -> None:
    client, provider = build_test_client(
        [json_response(_valid_stream(), model_id=PRIMARY_MODEL_ID)]
    )
    client.post("/v1/agent/surfaces", json={"task": "receipt", "context": {}})
    request = provider.last_request
    assert request.model_id == PRIMARY_MODEL_ID
    assert request.prompt_id == "interface_composition"
    assert request.prompt_version == "v2"
    assert request.decoding.temperature == 0.0
    assert "receipt" in request.contents


# --- Fallback behaviour (C-012: 200 with fallback on invalid composition) --------


def test_unknown_component_falls_back_but_stays_200() -> None:
    payload = {
        "messages": [
            {"type": "updateComponents", "components": [{"component": "EvilWidget", "id": "x"}]}
        ]
    }
    client, _ = build_test_client([json_response(payload, model_id=PRIMARY_MODEL_ID)])
    response = client.post("/v1/agent/surfaces", json={"task": "confirmation", "context": {}})
    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == []
    assert body["fallback"] == "confirmation"


def test_malformed_stream_falls_back() -> None:
    client, _ = build_test_client([json_response({"messages": "nope"}, model_id=PRIMARY_MODEL_ID)])
    response = client.post("/v1/agent/surfaces", json={"task": "amount_entry", "context": {}})
    assert response.status_code == 200
    assert response.json() == {"messages": [], "fallback": "amount_entry"}


def test_executable_content_falls_back() -> None:
    payload = {
        "messages": [
            {"type": "updateDataModel", "data": "<script>alert(1)</script>"},
        ]
    }
    client, _ = build_test_client([json_response(payload, model_id=PRIMARY_MODEL_ID)])
    response = client.post("/v1/agent/surfaces", json={"task": "receipt", "context": {}})
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_provider_failure_falls_back_to_the_same_task() -> None:
    client, _ = build_test_client([ProviderUnavailable("down")])
    response = client.post("/v1/agent/surfaces", json={"task": "discovery", "context": {}})
    assert response.status_code == 200
    assert response.json() == {"messages": [], "fallback": "discovery"}


# --- Client errors ---------------------------------------------------------------


def test_unknown_task_is_a_400() -> None:
    client, _ = build_test_client([])
    response = client.post("/v1/agent/surfaces", json={"task": "run_payment", "context": {}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_missing_task_is_rejected_with_the_error_envelope() -> None:
    client, _ = build_test_client([])
    response = client.post("/v1/agent/surfaces", json={"context": {}})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert "task" in body["error"]["message"]


def test_context_defaults_to_an_empty_object() -> None:
    client, _ = build_test_client([json_response(_valid_stream(), model_id=PRIMARY_MODEL_ID)])
    response = client.post("/v1/agent/surfaces", json={"task": "confirmation"})
    assert response.status_code == 200
    assert response.json()["fallback"] == "confirmation"


def test_context_may_carry_arbitrary_task_data() -> None:
    client, provider = build_test_client(
        [json_response(_valid_stream(), model_id=PRIMARY_MODEL_ID)]
    )
    context = {"receiptNumber": "FT-1", "kind": "official_e_receipt"}
    client.post("/v1/agent/surfaces", json={"task": "receipt", "context": context})
    assert "FT-1" in provider.last_request.contents


# --- Security --------------------------------------------------------------------


def test_unknown_task_does_not_echo_the_input() -> None:
    client, _ = build_test_client([])
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "<script>alert(1)</script>", "context": {}},
    )
    assert response.status_code == 400
    assert "<script>" not in response.text
