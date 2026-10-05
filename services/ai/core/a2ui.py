"""A2UI v0.9 message stream: parsing and agent-side pre-send validation.

The composed surface is an A2UI message stream (C-012 revision 2, MQ-003): a
``createSurface`` naming the negotiated ``catalogId``, a flat ``updateComponents``
list with identifier references and one ``root`` component, and an
``updateDataModel``. A2UI validates in two phases; this module is the agent-side
pre-send phase, run before the payload is sent so a hallucinated component or a
malformed message degrades to the same-task fallback rather than reaching the
client as a broken surface. The client repeats the validation on receipt
(FEAT-011).

Validation is deliberately structural and standalone: the catalog schema is JSON
Schema, but the checks here (known message type, version, catalog id, component
name, required properties, primitive property types, a referenced row component's
required properties, no executable content) are the ones the agent must never let
through, and they are the same checks the client's gate performs by name.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.a2ui_catalog import A2UI_VERSION, A2uiCatalog

# The A2UI v0.9 message bodies. The PascalCase action messages are not part of a
# composed surface stream.
MESSAGE_TYPES: frozenset[str] = frozenset(
    {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}
)

# A message body must be exactly one of these keys beside ``version``.
_MAX_BODY_KEYS = 1

_EXECUTABLE_PATTERNS = (
    "<script",
    "</script",
    "javascript:",
    "data:text/html",
    "<iframe",
    "<object",
    "<embed",
    "eval(",
    "function(",
    "onclick=",
    "onload=",
)
_EXTERNAL_LOAD_RE = re.compile(r"(?:https?://|//)[^\s\"']+", re.IGNORECASE)

_PRIMITIVE_TYPES: Mapping[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (Mapping,),
}


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, item in value.items():
            # The ``catalogId`` is an identifier, not a resource load: A2UI is
            # explicit that the URI is never fetched at runtime, so a ``https://``
            # catalog id must not trip the external-load rule.
            if key == "catalogId":
                continue
            found.extend(_walk_strings(item))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(_walk_strings(item))
        return found
    return []


def _is_executable_or_external(text: str) -> str | None:
    lowered = text.lower()
    if any(pattern in lowered for pattern in _EXECUTABLE_PATTERNS):
        return "executable content"
    if _EXTERNAL_LOAD_RE.search(text):
        return "external resource load"
    return None


def _resolve_component_ref(catalog: A2uiCatalog, ref: str) -> Mapping[str, Any] | None:
    """Resolve a catalog-local ``$ref`` (``#/components/<Name>``) to its schema.

    The published catalog is one JSON Schema document; an array property whose items
    are a ``$ref`` to a catalog component (``ProviderPicker.services`` items reference
    ``ServiceResultRow``) means every element must satisfy that component's schema,
    including its ``required`` properties. A reference that does not point at a catalog
    component returns ``None``: this structural pass cannot judge it, and the client's
    full schema validation remains the authority.
    """

    prefix = "#/components/"
    if not ref.startswith(prefix):
        return None
    schema = catalog.components.get(ref[len(prefix) :])
    return schema if isinstance(schema, Mapping) else None


def _object_items_schema(
    catalog: A2uiCatalog, items: Any
) -> tuple[Mapping[str, Any] | None, str | None]:
    """The schema and ``$ref`` for array items that are object-shaped.

    ``items`` may be a ``$ref`` to a catalog component or an inline object schema;
    both describe the element shape. A primitive ``items`` type yields ``(None, None)``
    and is not checked here.
    """

    if not isinstance(items, Mapping):
        return None, None
    ref = items.get("$ref")
    if isinstance(ref, str):
        return _resolve_component_ref(catalog, ref), ref
    if items.get("type") == "object" or "properties" in items or "required" in items:
        return items, None
    return None, None


def _check_object_against_schema(
    value: Mapping[str, Any],
    schema: Mapping[str, Any],
    what: str,
    errors: list[str],
    *,
    catalog: A2uiCatalog,
    seen: frozenset[str],
) -> None:
    """Check an object against a resolved component or inline object schema.

    Only the checks this structural pass can decide are made: the schema's ``required``
    names must be present and each present declared property must have the declared
    type. An absent optional property is not an error. ``seen`` carries the ``$ref``
    chain so a self-referential catalog cannot recurse forever.
    """

    required = schema.get("required")
    if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
        for name in required:
            if isinstance(name, str) and name not in value:
                errors.append(f"{what} is missing required {name!r}")
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for prop, declared in properties.items():
            if prop in value:
                _check_property_type(
                    value[prop],
                    declared,
                    f"{what} {prop!r}",
                    errors,
                    catalog=catalog,
                    seen=seen,
                )


def _check_property_type(
    value: Any,
    declared: Any,
    what: str,
    errors: list[str],
    *,
    catalog: A2uiCatalog,
    seen: frozenset[str] = frozenset(),
) -> None:
    """Check a value against a JSON-Schema ``type`` (string or list, nullable).

    A nested schema (a mapping, for example an array's ``items`` or a sub-object) is
    mostly left to the client's full schema validation; this pre-send pass checks only
    what it can decide without a JSON Schema engine. It does recurse into an array's
    ``items`` when the items declare an object shape, because a list of JSON-encoded
    strings where the catalog requires row objects passes the container check but
    renders nothing on the client: the client's picker drops a non-object entry, so the
    surface would be silently empty. When those items are a ``$ref`` to a catalog
    component, the referenced schema is resolved and every element is checked against
    its ``required`` properties too: a row of ``{}`` satisfies "is an object" but
    renders blank on the client, so it is refused here and the surface degrades to the
    same-task fallback instead (MQ-003, FEAT-011).
    """

    if value is None:
        # ``null`` is allowed when the declared type includes it; every catalog
        # property is otherwise optional in this structural pass, so a null on a
        # non-nullable field is reported below.
        if isinstance(declared, list) and "null" not in declared:
            errors.append(f"{what} must not be null")
        elif isinstance(declared, str):
            errors.append(f"{what} must not be null")
        return
    if isinstance(declared, Mapping):
        ref = declared.get("$ref")
        if isinstance(ref, str):
            # A component reference: resolve it and check the value against the
            # referenced component's schema. A reference outside the catalog is left
            # to the client's full schema validation.
            resolved = _resolve_component_ref(catalog, ref)
            if resolved is not None and ref not in seen:
                if not isinstance(value, Mapping):
                    errors.append(f"{what} must be an object")
                    return
                _check_object_against_schema(
                    value, resolved, what, errors, catalog=catalog, seen=seen | {ref}
                )
            return
        # A property schema object: check the declared ``type`` and, for an array of
        # object items, that each element is an object and (when the items resolve to
        # a component or an inline object schema) that it carries the required fields.
        _check_property_type(value, declared.get("type"), what, errors, catalog=catalog, seen=seen)
        items = declared.get("items")
        if _expects_object_items(declared.get("type"), items) and isinstance(value, (list, tuple)):
            item_schema, item_ref = _object_items_schema(catalog, items)
            for index, item in enumerate(value):
                if not isinstance(item, Mapping):
                    errors.append(f"{what}[{index}] must be an object")
                    continue
                if item_schema is None or (item_ref is not None and item_ref in seen):
                    continue
                _check_object_against_schema(
                    item,
                    item_schema,
                    f"{what}[{index}]",
                    errors,
                    catalog=catalog,
                    seen=(seen | {item_ref}) if item_ref is not None else seen,
                )
        return
    names = declared if isinstance(declared, list) else [declared]
    for name in names:
        if not isinstance(name, str) or name == "null":
            continue
        expected = _PRIMITIVE_TYPES.get(name)
        if expected is None:
            continue
        if isinstance(value, bool) and name in ("integer", "number"):
            continue  # a bool is not a number
        if isinstance(value, expected):
            return
    errors.append(f"{what} has the wrong type")


def _expects_object_items(declared_type: Any, items: Any) -> bool:
    """Whether an array property declares object-shaped items.

    ``items`` may be an inline object schema (``{"type": "object"}`` or a schema with
    properties) or a ``$ref`` to a catalog component; both mean the array's elements
    are objects. A primitive ``items`` type is not checked here.
    """

    if declared_type != "array":
        return False
    if not isinstance(items, Mapping):
        return False
    if "$ref" in items:
        return True
    item_type = items.get("type")
    return item_type == "object" or "properties" in items or "required" in items


@dataclass(frozen=True)
class StreamValidation:
    """The outcome of parsing and validating an A2UI stream against a catalog."""

    ok: bool
    errors: tuple[str, ...] = ()
    messages: tuple[Mapping[str, Any], ...] = ()
    component_names: tuple[str, ...] = ()
    surface_id: str | None = None


def validate_a2ui_stream(
    payload: Any,
    *,
    catalog: A2uiCatalog,
) -> StreamValidation:
    """Validate a model-composed A2UI stream against the published catalog.

    Returns a ``StreamValidation``: ``ok`` is true only when every message is a
    well-formed v0.9 message, every component is catalog-defined with its required
    properties present, the surface names the negotiated ``catalogId``, and one
    component carries ``id="root"``. Nothing raises; the caller turns a failure
    into the same-task fallback.
    """

    if not isinstance(payload, Mapping):
        return StreamValidation(ok=False, errors=("composition payload must be an object",))

    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
        return StreamValidation(ok=False, errors=("messages must be an array",))
    if not raw_messages:
        return StreamValidation(ok=False, errors=("messages must not be empty",))

    errors: list[str] = []
    messages: list[Mapping[str, Any]] = []
    component_names: list[str] = []
    surface_ids: list[str] = []
    saw_create_surface = False
    saw_root = False

    for index, raw in enumerate(raw_messages):
        if not isinstance(raw, Mapping):
            errors.append(f"message {index} is not an object")
            continue
        message = raw
        version = message.get("version")
        if version != A2UI_VERSION:
            errors.append(f"message {index} has version {version!r}, expected {A2UI_VERSION!r}")
            continue
        bodies = [key for key in message if key != "version"]
        if len(bodies) != _MAX_BODY_KEYS:
            errors.append(f"message {index} must carry exactly one message body")
            continue
        body_key = bodies[0]
        if body_key not in MESSAGE_TYPES:
            errors.append(f"message {index} has unknown type {body_key!r}")
            continue

        found = _walk_strings(message)
        for text in found:
            reason = _is_executable_or_external(text)
            if reason:
                errors.append(f"message {index} contains {reason}")
                break

        body = message.get(body_key)
        if not isinstance(body, Mapping):
            errors.append(f"message {index} body must be an object")
            continue

        if body_key == "createSurface":
            surface_id = body.get("surfaceId")
            if not isinstance(surface_id, str) or not surface_id:
                errors.append(f"message {index} createSurface requires a surfaceId")
            else:
                surface_ids.append(surface_id)
                saw_create_surface = True
            if body.get("catalogId") != catalog.catalog_id:
                errors.append(
                    f"message {index} createSurface must name the negotiated catalog "
                    f"{catalog.catalog_id!r}"
                )
        elif body_key == "updateComponents":
            surface_id = body.get("surfaceId")
            if isinstance(surface_id, str) and surface_id:
                surface_ids.append(surface_id)
            components = body.get("components")
            if not isinstance(components, Sequence) or isinstance(components, (str, bytes)):
                errors.append(f"message {index} updateComponents requires a components array")
                continue
            for component in components:
                name, is_root = _validate_component(
                    component, index=index, catalog=catalog, errors=errors
                )
                if name:
                    component_names.append(name)
                if is_root:
                    saw_root = True
        elif body_key == "updateDataModel":
            surface_id = body.get("surfaceId")
            if isinstance(surface_id, str) and surface_id:
                surface_ids.append(surface_id)
            if not isinstance(body.get("path"), str):
                errors.append(f"message {index} updateDataModel requires a path")
        messages.append(message)

    if not saw_create_surface:
        errors.append("the stream creates no surface")
    if not saw_root:
        errors.append('the surface has no "root" component')

    ok = not errors
    return StreamValidation(
        ok=ok,
        errors=tuple(errors),
        messages=tuple(messages) if ok else (),
        component_names=tuple(component_names),
        surface_id=surface_ids[0] if surface_ids else None,
    )


def _validate_component(
    component: Any,
    *,
    index: int,
    catalog: A2uiCatalog,
    errors: list[str],
) -> tuple[str | None, bool]:
    """Validate one flat component entry; return ``(name, is_root)``."""

    if not isinstance(component, Mapping):
        errors.append(f"message {index} has a component that is not an object")
        return None, False
    name = component.get("component")
    if not isinstance(name, str) or not name:
        errors.append(f"message {index} has a component with no type")
        return None, False
    if not catalog.defines(name):
        errors.append(f"message {index} requests unknown component {name!r}")
        return name, False
    component_id = component.get("id")
    if not isinstance(component_id, str) or not component_id:
        errors.append(f"message {index} component {name!r} needs a string id")

    for required in catalog.required_properties(name):
        if required not in component:
            errors.append(f"message {index} component {name!r} is missing required {required!r}")
            continue
        # Pass the full property schema, not just its ``type``: an array property's
        # object ``items`` (for example ``ProviderPicker.services``) is where a
        # non-object element is caught, and that detail is lost if only the type is
        # forwarded.
        declared_schema = catalog.property_types(name).get(required)
        if declared_schema is not None:
            _check_property_type(
                component[required],
                declared_schema,
                f"component {name!r} {required!r}",
                errors,
                catalog=catalog,
            )
    return name, component_id == "root"
