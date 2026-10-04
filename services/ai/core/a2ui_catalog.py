"""The published Sabi A2UI catalog, known to the agent at deploy time.

A2UI requires a ``catalogId`` to identify one published catalog that both the agent
and the client know before runtime; the URI is an identifier, never a runtime fetch
(A2UI "Catalog Naming & Versioning"). This module loads that published document from
``core/catalogs/sabi_a2ui_v1.json`` and exposes the component set and schemas the
agent composes and validates against, so the agent-side pre-send validation uses the
*same* catalog the client renders with rather than a private hand copy of names.

One catalog, two sides. The client owns the canonical document
(``apps/mobile/lib/a2ui/sabi_catalog.dart``); this JSON artifact is a byte-faithful
translation of it, and a guard test pins the two together. Editing a name here
without the client is the drift this module exists to prevent.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.errors import ModelError

# The A2UI wire version this catalog is spoken at (C-012 revision 2).
A2UI_VERSION = "v0.9"

_CATALOG_PATH = Path(__file__).parent / "catalogs" / "sabi_a2ui_v1.json"

# The A2UI catalog-schema keys a component definition may carry. The published
# document is validated against this shape at load, so a malformed or stale artifact
# fails loudly at boot rather than degrading a surface at request time.
_COMPONENT_SCHEMA_KEYS = frozenset(
    {"type", "description", "properties", "required", "additionalProperties"}
)


def _load_document() -> Mapping[str, Any]:
    try:
        raw = _CATALOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - absence is a packaging error
        raise ModelError(f"published catalog artifact not found: {_CATALOG_PATH.name}") from exc
    document = json.loads(raw)
    if not isinstance(document, Mapping):
        raise ModelError("published catalog must be an object")
    return document


@dataclass(frozen=True)
class A2uiCatalog:
    """A published A2UI catalog: one ``catalogId`` and its component schemas.

    ``components`` maps a component name to its JSON Schema. The catalog is
    additive-only and its enums are open (A2UI evolution rules), so an unknown
    enum variant is tolerated while an unknown component name is refused.
    """

    catalog_id: str
    components: Mapping[str, Mapping[str, Any]]

    def defines(self, name: str) -> bool:
        """Whether this catalog defines ``name``."""

        return name in self.components

    def component_names(self) -> tuple[str, ...]:
        """The component names, in catalog order."""

        return tuple(self.components)

    def required_properties(self, name: str) -> tuple[str, ...]:
        """The JSON-Schema ``required`` properties of a component, if any."""

        schema = self.components.get(name) or {}
        required = schema.get("required") or ()
        return tuple(str(item) for item in required)

    def property_types(self, name: str) -> Mapping[str, Any]:
        """The component's ``properties`` schema, for pre-send type checks."""

        schema = self.components.get(name) or {}
        properties = schema.get("properties") or {}
        return properties if isinstance(properties, Mapping) else {}


def _build_catalog(document: Mapping[str, Any]) -> A2uiCatalog:
    catalog_id = document.get("catalogId")
    if not isinstance(catalog_id, str) or not catalog_id:
        raise ModelError("published catalog is missing catalogId")
    if document.get("$id") != catalog_id:
        # A2UI requires the schema document's ``$id`` and its ``catalogId`` to be
        # the same URI.
        raise ModelError("published catalog $id and catalogId must match")

    components = document.get("components")
    if not isinstance(components, Mapping) or not components:
        raise ModelError("published catalog defines no components")

    normalised: dict[str, Mapping[str, Any]] = {}
    for name, schema in components.items():
        if not isinstance(name, str) or not name:
            raise ModelError("published catalog has a non-string component name")
        if not isinstance(schema, Mapping):
            raise ModelError(f"component {name} is not an object schema")
        unknown = set(schema) - _COMPONENT_SCHEMA_KEYS
        if unknown:
            raise ModelError(f"component {name} carries unexpected schema keys: {sorted(unknown)}")
        if schema.get("type") != "object":
            raise ModelError(f"component {name} must declare type object")
        normalised[name] = dict(schema)
    return A2uiCatalog(catalog_id=catalog_id, components=normalised)


@lru_cache(maxsize=1)
def published_catalog() -> A2uiCatalog:
    """The published Sabi catalog, loaded once per process."""

    return _build_catalog(_load_document())


def supported_catalog_ids() -> tuple[str, ...]:
    """The catalog ids the agent can speak, in preference order.

    This mirrors the A2UI negotiation: the agent selects from the client's
    ``supportedCatalogIds``. One catalog is published today; the tuple is the
    single place a second version is added for a migration.
    """

    return (published_catalog().catalog_id,)


def negotiate_catalog(catalog_id: str | None) -> A2uiCatalog | None:
    """Select the catalog for a request, or ``None`` when none is compatible.

    A2UI negotiation: the agent selects the best match from the catalog id the
    client advertised. No compatible catalog means the agent sends no surface and
    the client renders its fallback for the same task (A2UI "Agent Selection";
    FEAT-011 edge case). An absent id is not compatible, because the agent must
    not compose against a catalog the client did not name.
    """

    if not catalog_id:
        return None
    resolved = catalog_id.strip()
    for supported in supported_catalog_ids():
        if resolved == supported:
            return published_catalog()
    return None
