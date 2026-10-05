"""Contract conformance for POST /v1/agent/surfaces (C-012, MQ-003).

The model is mocked in every test, so the suite is deterministic and never
touches the network or the google-genai SDK. The composed payload is a real A2UI
v0.9 stream composed against the published Sabi catalog; the agent validates it
before sending (the agent-side phase of A2UI's two-phase validation).
"""

from __future__ import annotations

from composition.tests.conftest import build_test_client
from core.a2ui_catalog import published_catalog
from core.config import FLASH_MODEL_ID
from core.errors import ProviderUnavailable
from core.schemas import FALLBACK_TASKS
from core.testing import json_response

_HEADERS = {"Content-Type": "application/json"}
_CATALOG_ID = published_catalog().catalog_id


def _a2ui(surface_id: str, components: list[dict], *, data: dict | None = None) -> dict:
    """A well-formed A2UI v0.9 stream naming the published catalog."""

    messages: list[dict] = [
        {"version": "v0.9", "createSurface": {"surfaceId": surface_id, "catalogId": _CATALOG_ID}},
        {
            "version": "v0.9",
            "updateComponents": {"surfaceId": surface_id, "components": components},
        },
    ]
    if data is not None:
        messages.append(
            {
                "version": "v0.9",
                "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": data},
            }
        )
    return {"messages": messages}


def _verification_stream() -> dict:
    return _a2ui(
        "verify-1",
        [{"id": "root", "component": "Verification", "title": "Verify your identity"}],
        data={"status": "unverified"},
    )


def _recovery_stream() -> dict:
    return _a2ui(
        "case-1",
        [{"id": "root", "component": "Recovery", "title": "Refund in progress"}],
        data={"caseReference": "CASE-7", "state": "refunding"},
    )


def _record_receipt_stream() -> dict:
    return _a2ui(
        "receipt-1",
        [
            {
                "id": "root",
                "component": "ReceiptCard",
                "reference": "FT-2026-1",
                "payee": "FIRS",
                "amount": 500000,
            }
        ],
        data={"receiptId": "rcpt-9", "kind": "token"},
    )


def _valid_stream() -> dict:
    return _a2ui(
        "confirm-1",
        [
            {
                "id": "root",
                "component": "ConfirmationSummary",
                "amount": 500000,
                "payee": "Ikeja Electric",
            }
        ],
    )


def _discovery_stream() -> dict:
    """A multi-result ProviderPicker, the shape a live discovery composes."""

    return _a2ui(
        "discover-1",
        [
            {
                "id": "root",
                "component": "ProviderPicker",
                "services": [
                    {
                        "serviceId": "s1",
                        "name": "Ikeja Electric",
                        "collectingBody": "Ikeja Electric",
                        "category": "electricity",
                        "status": "active",
                    },
                    {
                        "serviceId": "s2",
                        "name": "Eko Electric",
                        "collectingBody": "EKEDC",
                        "category": "electricity",
                        "status": "active",
                    },
                ],
            }
        ],
    )


# The exact multi-result discovery context the client and the gateway probe send:
# candidate rows under `services`, matching the catalog's ProviderPicker property.
# The agent-only `results` key once used by mocked fixtures made every real discovery
# fall back on missing context before the model was ever asked (FEAT-011, MQ-003).
_GATEWAY_DISCOVERY_CONTEXT = {
    "services": [
        {
            "serviceId": "s1",
            "name": "Ikeja Electric",
            "collectingBody": "Ikeja Electric",
            "category": "electricity",
            "status": "active",
        },
        {
            "serviceId": "s2",
            "name": "Eko Electric",
            "collectingBody": "EKEDC",
            "category": "electricity",
            "status": "active",
        },
    ]
}


# --- Happy path ------------------------------------------------------------------


def test_composes_a_catalogue_valid_surface() -> None:
    client, _ = build_test_client([json_response(_valid_stream(), model_id=FLASH_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces",
        json={
            "task": "confirmation",
            "context": {"amount": 500000, "payee": "Ikeja Electric"},
            "catalogId": _CATALOG_ID,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [next(k for k in message if k != "version") for message in body["messages"]] == [
        "createSurface",
        "updateComponents",
    ]
    assert body["messages"][0]["createSurface"]["catalogId"] == _CATALOG_ID
    assert body["fallback"] == "confirmation"


def test_composes_a_multi_result_discovery_from_the_gateway_context_shape() -> None:
    """A multi-result discovery sent as the client/gateway does reaches the model.

    Regression: the serving guard required a `results` context key no client ever
    sent, so the gateway forwards the client's `services` shape and every live
    discovery degraded to the same-task fallback before the model was asked while
    this suite stayed green. The multi-result ProviderPicker stream must compose.
    """

    client, provider = build_test_client(
        [json_response(_discovery_stream(), model_id=FLASH_MODEL_ID)]
    )
    response = client.post(
        "/v1/agent/surfaces",
        json={
            "task": "discovery",
            "context": _GATEWAY_DISCOVERY_CONTEXT,
            "catalogId": _CATALOG_ID,
        },
    )
    assert response.status_code == 200
    body = response.json()
    # The model was reached (not the missing-context fallback) and its stream is
    # returned; a fallback here with a non-empty ProviderPicker fixture means the
    # context shape was refused before composition.
    assert len(provider.requests) == 1
    assert provider.last_request is not None
    assert body["fallback"] == "discovery"
    assert len(body["messages"]) > 0
    assert body["messages"][1]["updateComponents"]["components"][0]["component"] == (
        "ProviderPicker"
    )
    # Both candidate rows reach the prompt, so the model composes the real picker.
    assert "s1" in provider.last_request.contents
    assert "s2" in provider.last_request.contents


def test_composes_a_verification_surface() -> None:
    client, provider = build_test_client(
        [json_response(_verification_stream(), model_id=FLASH_MODEL_ID)]
    )
    response = client.post(
        "/v1/agent/surfaces",
        json={
            "task": "verification",
            "context": {"status": "unverified"},
            "catalogId": _CATALOG_ID,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] == "verification"
    assert "verification" in provider.last_request.contents


def test_composes_a_recovery_surface() -> None:
    client, _ = build_test_client([json_response(_recovery_stream(), model_id=FLASH_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "recovery", "context": {"status": "refunding"}, "catalogId": _CATALOG_ID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] == "recovery"
    assert [next(k for k in message if k != "version") for message in body["messages"]] == [
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
        [json_response(_record_receipt_stream(), model_id=FLASH_MODEL_ID)]
    )
    context = {
        "recordKind": "receipt",
        "reference": "FT-2026-1",
        "receiptId": "rcpt-9",
        "payee": "FIRS",
        "amount": 500000,
    }
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "receipt", "context": context, "catalogId": _CATALOG_ID},
    )
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
        client, _ = build_test_client([json_response(_valid_stream(), model_id=FLASH_MODEL_ID)])
        response = client.post(
            "/v1/agent/surfaces", json={"task": task, "context": {}, "catalogId": _CATALOG_ID}
        )
        assert response.status_code == 200, task
        assert response.json()["fallback"] == task


def test_invalid_composition_keeps_the_new_task_fallback() -> None:
    payload = _a2ui("s1", [{"id": "root", "component": "EvilWidget"}])
    client, _ = build_test_client([json_response(payload, model_id=FLASH_MODEL_ID)])
    for task in ("verification", "recovery"):
        response = client.post(
            "/v1/agent/surfaces", json={"task": task, "context": {}, "catalogId": _CATALOG_ID}
        )
        assert response.status_code == 200
        assert response.json() == {"messages": [], "fallback": task}


def test_composition_runs_on_the_pinned_primary_model_and_prompt() -> None:
    client, provider = build_test_client(
        [json_response(_valid_stream(), model_id=FLASH_MODEL_ID)]
    )
    client.post(
        "/v1/agent/surfaces",
        json={
            "task": "receipt",
            "context": {"reference": "FT-1", "payee": "FIRS", "amount": 100},
            "catalogId": _CATALOG_ID,
        },
    )
    request = provider.last_request
    assert request.model_id == FLASH_MODEL_ID
    assert request.prompt_id == "interface_composition"
    assert request.prompt_version == "v5"
    assert request.decoding.temperature == 0.0
    assert _CATALOG_ID in request.contents
    assert "Verification" in request.contents and "Recovery" in request.contents
    # The provider is constrained by the catalog-derived JSON schema, not the open
    # object schema that permitted an empty message body (MQ-003).
    schema = request.response_json_schema
    assert schema is not None
    messages = schema["properties"]["messages"]
    assert messages["minItems"] >= 1
    assert messages["items"]["required"] == ["version"]


# --- Catalog negotiation (C-012: fallback, not a failure) ------------------------


def test_no_compatible_catalog_falls_back_to_the_same_task() -> None:
    """No compatible catalog negotiated -> same-task fallback, never an error."""

    client, provider = build_test_client([])
    for catalog_id in (None, "", "https://other.example/a2ui/v9/catalog.json"):
        body = {"task": "discovery", "context": {}}
        if catalog_id is not None:
            body["catalogId"] = catalog_id
        response = client.post("/v1/agent/surfaces", json=body)
        assert response.status_code == 200
        assert response.json() == {"messages": [], "fallback": "discovery"}
    # The agent never called the model when it had no catalog to compose against.
    assert provider.requests == []


def test_unknown_catalog_does_not_call_the_model() -> None:
    client, provider = build_test_client(
        [json_response(_valid_stream(), model_id=FLASH_MODEL_ID)]
    )
    client.post(
        "/v1/agent/surfaces",
        json={"task": "confirmation", "context": {}, "catalogId": "https://nope/catalog.json"},
    )
    assert provider.requests == []


# --- Fallback behaviour (C-012: 200 with fallback on invalid composition) --------


def test_unknown_component_falls_back_but_stays_200() -> None:
    payload = _a2ui("s1", [{"id": "root", "component": "EvilWidget"}])
    client, _ = build_test_client([json_response(payload, model_id=FLASH_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces", json={"task": "confirmation", "context": {}, "catalogId": _CATALOG_ID}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == []
    assert body["fallback"] == "confirmation"


def test_malformed_stream_falls_back() -> None:
    client, _ = build_test_client([json_response({"messages": "nope"}, model_id=FLASH_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces", json={"task": "amount_entry", "context": {}, "catalogId": _CATALOG_ID}
    )
    assert response.status_code == 200
    assert response.json() == {"messages": [], "fallback": "amount_entry"}


def test_executable_content_falls_back() -> None:
    payload = _a2ui(
        "s1",
        [
            {
                "id": "root",
                "component": "ReceiptCard",
                "reference": "<script>alert(1)</script>",
                "payee": "x",
                "amount": 1,
            }
        ],
    )
    client, _ = build_test_client([json_response(payload, model_id=FLASH_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces", json={"task": "receipt", "context": {}, "catalogId": _CATALOG_ID}
    )
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_provider_failure_falls_back_to_the_same_task() -> None:
    client, _ = build_test_client([ProviderUnavailable("down")])
    response = client.post(
        "/v1/agent/surfaces", json={"task": "discovery", "context": {}, "catalogId": _CATALOG_ID}
    )
    assert response.status_code == 200
    assert response.json() == {"messages": [], "fallback": "discovery"}


# --- Client errors ---------------------------------------------------------------


def test_unknown_task_is_a_400() -> None:
    client, _ = build_test_client([])
    response = client.post(
        "/v1/agent/surfaces", json={"task": "run_payment", "context": {}, "catalogId": _CATALOG_ID}
    )
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
    client, _ = build_test_client([json_response(_valid_stream(), model_id=FLASH_MODEL_ID)])
    response = client.post(
        "/v1/agent/surfaces", json={"task": "confirmation", "catalogId": _CATALOG_ID}
    )
    assert response.status_code == 200
    assert response.json()["fallback"] == "confirmation"


def test_context_may_carry_arbitrary_task_data() -> None:
    client, provider = build_test_client(
        [json_response(_valid_stream(), model_id=FLASH_MODEL_ID)]
    )
    context = {
        "reference": "FT-1",
        "payee": "FIRS",
        "amount": 100,
        "kind": "official_e_receipt",
    }
    client.post(
        "/v1/agent/surfaces",
        json={"task": "receipt", "context": context, "catalogId": _CATALOG_ID},
    )
    assert "FT-1" in provider.last_request.contents


def test_missing_task_context_falls_back_without_calling_the_model() -> None:
    """A caller that omits a task's required fields degrades explicitly (C-012, FEAT-011).

    The confirmation context carries `amount` but no `payee`: the exact input that,
    under the contradictory prompt, made the model emit an empty stream. The serving
    layer now returns the same-task fallback before the model is asked, so the failure
    is a logged server decision, not a silent empty model response.
    """

    client, provider = build_test_client(
        [json_response(_valid_stream(), model_id=FLASH_MODEL_ID)]
    )
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "confirmation", "context": {"amount": 500000}, "catalogId": _CATALOG_ID},
    )
    assert response.status_code == 200
    assert response.json() == {"messages": [], "fallback": "confirmation"}
    assert provider.requests == []


def test_missing_context_fallback_applies_to_every_task() -> None:
    """An empty context never composes a surface and never reaches the model."""

    for task in sorted(FALLBACK_TASKS):
        client, provider = build_test_client([])
        response = client.post(
            "/v1/agent/surfaces", json={"task": task, "context": {}, "catalogId": _CATALOG_ID}
        )
        assert response.status_code == 200, task
        assert response.json() == {"messages": [], "fallback": task}
        assert provider.requests == [], task


# --- Security --------------------------------------------------------------------


def test_unknown_task_does_not_echo_the_input() -> None:
    client, _ = build_test_client([])
    response = client.post(
        "/v1/agent/surfaces",
        json={"task": "<script>alert(1)</script>", "context": {}},
    )
    assert response.status_code == 400
    assert "<script>" not in response.text
