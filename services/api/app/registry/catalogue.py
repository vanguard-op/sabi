"""Client component catalogue and the approved input-schema set.

A capability's declared input schema is checked against the components the
client actually exposes (FEAT-011, FEAT-012): a capability that requires a
component outside the catalogue is never offered to users and is rejected at
submission with a 422. The component names mirror the client catalogue
(``apps/mobile/lib/components/composed_task_surface.dart``), which is the only
place they are rendered.

The approved schemas live here because the registry owns schema versioning and
review (architecture.md, Capability Registry). A schema is referenced by an
opaque ``inputSchemaRef``; an unknown reference is an invalid schema.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.core.errors import APIError, ErrorCode

# The types the client renders. Kept in step with the composed-surface renderer;
# an agent message naming anything else falls back to a plain form.
CLIENT_COMPONENTS: frozenset[str] = frozenset(
    {
        "text",
        "confirmationSummary",
        "serviceResultRow",
        "receiptCard",
        "statusPill",
        "amountEntry",
    }
)


@dataclass(frozen=True, slots=True)
class InputSchema:
    """An approved input schema: its reference and the components it needs."""

    ref: str
    components: frozenset[str]


class SchemaCatalog:
    """Resolves an ``inputSchemaRef`` to its declared client components."""

    def __init__(self, schemas: Iterable[InputSchema] = ()) -> None:
        self._schemas: Mapping[str, InputSchema] = MappingProxyType({s.ref: s for s in schemas})

    def validate(self, ref: str) -> InputSchema:
        """Return the schema for ``ref`` or raise a 422 for an unusable one."""
        schema = self._schemas.get(ref)
        if schema is None:
            raise APIError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "The input schema reference is not recognised.",
            )
        outside = schema.components - CLIENT_COMPONENTS
        if outside:
            # A capability outside the client catalogue is never offered
            # (FEAT-012); reject it before it can be reviewed.
            raise APIError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "The input schema needs a component the client does not expose.",
                {"components": sorted(outside)},
            )
        return schema


# Phase 1 approved input schemas. Additional schemas join this set through the
# same review the capabilities that use them pass.
APPROVED_INPUT_SCHEMAS: tuple[InputSchema, ...] = (
    InputSchema(
        ref="sabi:input/service-payment",
        components=frozenset({"text", "amountEntry", "confirmationSummary"}),
    ),
    InputSchema(
        ref="sabi:input/service-query",
        components=frozenset({"text", "serviceResultRow", "confirmationSummary"}),
    ),
)

DEFAULT_SCHEMA_CATALOG = SchemaCatalog(APPROVED_INPUT_SCHEMAS)
