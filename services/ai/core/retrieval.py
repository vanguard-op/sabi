"""Retrieval and untrusted-content handling for grounding.

The retrieval index returns Sabi's own catalogue records; the model never supplies
facts about services, amounts, or references from memory. Retrieved content is
untrusted: it is rendered inside explicit delimiters, any delimiter appearing in the
content is escaped, and it can never override the instructions in the prompt.

The concrete lexical index here is deterministic and dependency-free. The production
vector index (pgvector) implements the same :class:`RetrievalIndex` protocol and is
wired by the catalogue owner.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "i",
        "in",
        "is",
        "it",
        "my",
        "of",
        "on",
        "the",
        "to",
        "wan",
    }
)

_BLOCK_START = "<<<RETRIEVED_DATA"
_BLOCK_END = "<<<END_RETRIEVED_DATA>>>"


@dataclass(frozen=True)
class RetrievedRecord:
    """One grounding record from the catalogue or receipt store."""

    record_id: str
    kind: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    source: str = "catalogue"

    @classmethod
    def from_service(
        cls, service: Mapping[str, Any], *, source: str = "catalogue"
    ) -> RetrievedRecord:
        """Build a record from a catalogue service payload."""

        record_id = str(service.get("service_id") or service.get("id") or "")
        if not record_id:
            raise ValueError("service record requires a service_id")
        return cls(record_id=record_id, kind="service", fields=dict(service), source=source)

    @property
    def service_id(self) -> str | None:
        value = self.fields.get("service_id") or self.fields.get("id")
        return str(value) if value else None

    @property
    def known_amount(self) -> int | None:
        value = self.fields.get("known_amount")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def reference(self) -> str | None:
        value = self.fields.get("reference")
        return str(value) if value else None


class RetrievalIndex(Protocol):
    """Nearest-neighbour or lexical search over grounding content."""

    def search(self, query: str, *, limit: int) -> Sequence[RetrievedRecord]: ...


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


def _searchable_text(record: RetrievedRecord) -> str:
    fields = record.fields
    parts: list[str] = [record.record_id]
    for key in ("name", "collecting_body", "category", "aliases", "obligation"):
        value = fields.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            parts.extend(str(item) for item in value)
    return " ".join(parts)


class KeywordRetrievalIndex:
    """Deterministic lexical index over a fixed set of records.

    Ranking is by token overlap; ties break on record id so results are stable
    between runs. A query with no overlap returns nothing rather than a best guess.
    """

    def __init__(self, records: Sequence[RetrievedRecord]) -> None:
        self._records = list(records)
        self._tokens: dict[str, frozenset[str]] = {
            record.record_id: frozenset(_tokens(_searchable_text(record)))
            for record in self._records
        }

    def search(self, query: str, *, limit: int) -> list[RetrievedRecord]:
        query_tokens = set(_tokens(query))
        if not query_tokens or limit <= 0:
            return []
        scored: list[tuple[int, str, RetrievedRecord]] = []
        for record in self._records:
            overlap = len(query_tokens & self._tokens[record.record_id])
            if overlap:
                scored.append((overlap, record.record_id, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [record for _, _, record in scored[:limit]]


def render_untrusted_block(records: Sequence[RetrievedRecord]) -> str:
    """Render records as a delimited, escaped block of untrusted data.

    The end delimiter is neutralised inside any value so retrieved content cannot
    close the block early and smuggle instructions into the prompt.
    """

    lines: list[str] = [_BLOCK_START]
    for record in records:
        lines.append(f"record_id={_neutralise(record.record_id)} kind={record.kind}")
        for key in sorted(record.fields):
            lines.append(f"  {key}={_neutralise(record.fields[key])}")
    lines.append(_BLOCK_END)
    return "\n".join(lines)


def _neutralise(value: Any) -> str:
    text = str(value)
    return text.replace("<<<", "< <<").replace(">>>", "> >>")
