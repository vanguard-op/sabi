"""Tests for the published Sabi A2UI catalog and its negotiation.

The catalog is the single source of truth both sides validate against, so these
tests pin it to the published contract: the id, the component set, the shell names
that are deliberately absent, and the negotiation result. A mismatch here is the
drift that a server-side hand copy of the client's names used to introduce.
"""

from __future__ import annotations

import pytest

from core.a2ui_catalog import (
    A2UI_VERSION,
    negotiate_catalog,
    published_catalog,
    supported_catalog_ids,
)
from core.errors import ModelError

# The composed surfaces the published catalog exposes (FEAT-011, MQ-003). The shell
# names are deliberately absent: the composer, navigation, static chrome, and fixed
# buttons and labels are prewritten client code, never composed.
_PUBLISHED_COMPONENTS = (
    "ConfirmationSummary",
    "AmountEntry",
    "ProviderPicker",
    "ServiceResultRow",
    "ReceiptCard",
    "StatusPill",
    "Verification",
    "Recovery",
)
_SHELL_NAMES = (
    "NavigationShell",
    "ComposedTaskSurface",
    "EmptyState",
    "ErrorState",
    "OfflineBanner",
    "SuccessToast",
)


def test_catalog_id_is_the_published_uri():
    catalog = published_catalog()
    assert catalog.catalog_id == "https://sabi.app/a2ui/v1/catalog.json"
    # A2UI requires the document $id and the catalogId to be the same URI.
    assert catalog.catalog_id in supported_catalog_ids()


def test_catalog_covers_exactly_the_composed_surfaces_and_not_the_shell():
    catalog = published_catalog()
    assert catalog.component_names() == _PUBLISHED_COMPONENTS
    for shell in _SHELL_NAMES:
        assert catalog.defines(shell) is False, shell


def test_catalog_declares_required_properties_for_the_payment_surfaces():
    catalog = published_catalog()
    # The agent's pre-send validation reads these; a component that silently lost
    # its required fields would let an incomplete surface through.
    assert catalog.required_properties("ConfirmationSummary") == ("amount", "payee")
    assert set(catalog.required_properties("ReceiptCard")) == {"reference", "payee", "amount"}
    assert catalog.required_properties("StatusPill") == ("status",)


def test_negotiate_returns_the_published_catalog_for_its_id():
    catalog = negotiate_catalog("https://sabi.app/a2ui/v1/catalog.json")
    assert catalog is not None
    assert catalog.catalog_id == published_catalog().catalog_id


@pytest.mark.parametrize(
    "catalog_id",
    [None, "", "   ", "https://sabi.app/a2ui/v2/catalog.json", "https://other.example/x.json"],
)
def test_no_compatible_catalog_negotiates_to_none(catalog_id):
    # An absent id is not compatible: the agent must not compose against a catalog
    # the client did not name (A2UI "Agent Selection").
    assert negotiate_catalog(catalog_id) is None


def test_a2ui_wire_version_is_pinned():
    assert A2UI_VERSION == "v0.9"


def test_catalog_loads_once_and_is_immutable():
    first = published_catalog()
    second = published_catalog()
    assert first is second
    with pytest.raises(AttributeError):
        first.catalog_id = "changed"  # type: ignore[misc]


def test_catalog_rejects_a_document_whose_id_and_catalog_id_differ():
    from core.a2ui_catalog import _build_catalog

    with pytest.raises(ModelError):
        _build_catalog(
            {"$id": "https://a/x.json", "catalogId": "https://b/x.json", "components": {}}
        )
