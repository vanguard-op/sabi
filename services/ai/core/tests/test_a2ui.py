"""Tests for A2UI stream parsing and the agent-side pre-send validation.

The validation decides whether a composed surface is sent or degrades to the
same-task fallback, so these cases are the ones that keep a hallucinated component
or a malformed message from reaching the client (MQ-003, FEAT-011).
"""

from __future__ import annotations

import pytest

from core.a2ui import MESSAGE_TYPES, validate_a2ui_stream
from core.a2ui_catalog import published_catalog

_CATALOG = published_catalog()
_CATALOG_ID = _CATALOG.catalog_id


def _confirmation_stream(**component_overrides):
    component = {
        "id": "root",
        "component": "ConfirmationSummary",
        "amount": 500000,
        "payee": "Ikeja Electric",
    }
    component.update(component_overrides)
    return {
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": "s1", "catalogId": _CATALOG_ID}},
            {"version": "v0.9", "updateComponents": {"surfaceId": "s1", "components": [component]}},
        ]
    }


def _validate(payload):
    return validate_a2ui_stream(payload, catalog=_CATALOG)


def test_a_well_formed_stream_passes():
    result = _validate(_confirmation_stream())
    assert result.ok is True
    assert result.errors == ()
    assert result.surface_id == "s1"
    assert result.component_names == ("ConfirmationSummary",)
    assert len(result.messages) == 2


def test_message_types_are_the_a2ui_v09_bodies():
    assert MESSAGE_TYPES == {
        "createSurface",
        "updateComponents",
        "updateDataModel",
        "deleteSurface",
    }


def test_unknown_component_is_rejected():
    result = _validate(_confirmation_stream(component="EvilWidget"))
    assert result.ok is False
    assert any("unknown component" in error for error in result.errors)
    assert result.messages == ()


def test_surface_naming_another_catalog_is_rejected():
    payload = _confirmation_stream()
    payload["messages"][0]["createSurface"]["catalogId"] = "https://other.example/x.json"
    result = _validate(payload)
    assert result.ok is False
    assert any("negotiated catalog" in error for error in result.errors)


def test_missing_required_property_is_rejected():
    payload = _confirmation_stream()
    del payload["messages"][1]["updateComponents"]["components"][0]["payee"]
    result = _validate(payload)
    assert result.ok is False
    assert any("missing required 'payee'" in error for error in result.errors)


def test_wrong_property_type_is_rejected():
    result = _validate(_confirmation_stream(amount="five hundred thousand"))
    assert result.ok is False
    assert any("wrong type" in error for error in result.errors)


def test_a_bare_bool_is_not_an_integer_amount():
    result = _validate(_confirmation_stream(amount=True))
    assert result.ok is False
    assert any("wrong type" in error for error in result.errors)


def test_a_surface_without_a_root_component_is_rejected():
    payload = _confirmation_stream(id="not-root")
    result = _validate(payload)
    assert result.ok is False
    assert any("root" in error for error in result.errors)


def test_a_stream_without_a_create_surface_is_rejected():
    payload = _confirmation_stream()
    payload["messages"] = [payload["messages"][1]]
    result = _validate(payload)
    assert result.ok is False
    assert any("creates no surface" in error for error in result.errors)


def test_wrong_wire_version_is_rejected():
    payload = _confirmation_stream()
    payload["messages"][0]["version"] = "v0.8"
    result = _validate(payload)
    assert result.ok is False
    assert any("version" in error for error in result.errors)


def test_a_message_may_not_carry_two_bodies():
    payload = _confirmation_stream()
    payload["messages"][0]["updateComponents"] = {"surfaceId": "s1", "components": []}
    result = _validate(payload)
    assert result.ok is False
    assert any("exactly one message body" in error for error in result.errors)


def test_non_object_message_is_rejected():
    payload = {"messages": ["not-an-object"]}
    result = _validate(payload)
    assert result.ok is False
    assert any("not an object" in error for error in result.errors)


def test_empty_or_missing_messages_is_rejected():
    assert _validate({"messages": []}).ok is False
    assert _validate({}).ok is False
    assert _validate("nope").ok is False


def test_executable_content_is_rejected():
    payload = _confirmation_stream(payee="<script>alert(1)</script>")
    result = _validate(payload)
    assert result.ok is False
    assert any("executable content" in error for error in result.errors)


def test_an_external_load_in_data_is_rejected():
    payload = {
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": "s1", "catalogId": _CATALOG_ID}},
            {
                "version": "v0.9",
                "updateDataModel": {
                    "surfaceId": "s1",
                    "path": "/",
                    "value": "https://evil.example/x.js",
                },
            },
        ]
    }
    result = _validate(payload)
    assert result.ok is False
    assert any("external resource load" in error for error in result.errors)


def test_the_catalog_uri_is_not_treated_as_an_external_load():
    # The catalogId is an identifier, not a fetched resource (A2UI is explicit the
    # URI is never fetched), so it must not trip the external-load rule.
    result = _validate(_confirmation_stream())
    assert result.ok is True


def test_provider_picker_accepts_nested_service_rows():
    payload = {
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": "d1", "catalogId": _CATALOG_ID}},
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "d1",
                    "components": [
                        {
                            "id": "root",
                            "component": "ProviderPicker",
                            "services": [
                                {
                                    "serviceId": "svc-1",
                                    "collectingBody": "Lagos State Government",
                                    "category": "government",
                                }
                            ],
                        }
                    ],
                },
            },
        ]
    }
    result = _validate(payload)
    assert result.ok is True


def test_a_null_on_a_nullable_property_is_accepted():
    payload = {
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": "s1", "catalogId": _CATALOG_ID}},
            {
                "version": "v0.9",
                "updateComponents": {
                    "surfaceId": "s1",
                    "components": [
                        {"id": "root", "component": "AmountEntry", "minimum": None, "maximum": None}
                    ],
                },
            },
        ]
    }
    assert _validate(payload).ok is True


@pytest.mark.parametrize("bad", [None, "", 123])
def test_create_surface_requires_a_surface_id(bad):
    payload = {
        "messages": [
            {"version": "v0.9", "createSurface": {"surfaceId": bad, "catalogId": _CATALOG_ID}},
        ]
    }
    result = _validate(payload)
    assert result.ok is False
