"""Idempotent load of the version-controlled service catalogue.

The assistant grounds every fact on the catalogue, so an empty catalogue is why a
request like "Ikeja" resolves to nothing. This module loads the real Nigerian
payable services held in a version-controlled data file into the primary store,
so the owner never hand-enters them and every environment is grounded on the same
records (FEAT-004, FEAT-012; D-048).

The catalogue is public, non-secret data, unlike the staff credential the dev
seed provisions, so this seed deliberately carries no environment guard: a
hosted staging load is intended. The safety comes from the data, not the
environment. The file names only public organisations and services; it holds no
personal data and no secret, and it is safe to run anywhere the primary store is
writable.

Idempotency is by the natural key ``(name, collecting_body)``, compared
case-insensitively. A re-run updates the existing row in place and never creates
a duplicate, and the result reports how many rows were created, updated, and left
unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Service

# The categories in the seed data are free-form (electricity, airtime, data,
# tax, levy, fee), matching the schema's ``category`` grouping used by discovery.
_ALLOWED_TYPES = ("government", "biller", "merchant")
_ALLOWED_STATUSES = ("active", "unavailable", "retired")

#: The service's maximal name length (schema.md ``Service.name`` maxLength).
_MAX_NAME_LENGTH = 200

#: Default data file, resolved relative to ``services/api`` so the module is
#: importable without a working directory assumption.
DEFAULT_CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "data" / "catalogue.json"


class SeedError(RuntimeError):
    """Raised when the catalogue data file is missing or malformed."""


@dataclass(frozen=True)
class CatalogueEntry:
    """One catalogue row as read from the data file.

    ``known_amount`` is ``None`` when the source provides no fixed amount; the
    seed never invents one (FEAT-004). Amounts are integer minor units.
    """

    type: str
    name: str
    collecting_body: str
    category: str
    aliases: tuple[str, ...]
    known_amount: int | None
    currency: str
    status: str


@dataclass(frozen=True)
class SeedResult:
    """What a load did, so the operator and tests can assert idempotency."""

    created: int
    updated: int
    skipped: int
    total: int


def load_entries(path: Path | str = DEFAULT_CATALOGUE_PATH) -> list[CatalogueEntry]:
    """Read and validate the catalogue data file.

    Fails loudly on a missing file, invalid JSON, or a row that would violate the
    schema, so a bad reload never writes partial data.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise SeedError(f"Catalogue data file not found: {resolved}")

    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SeedError(f"Catalogue data file is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("services"), list):
        raise SeedError("Catalogue data file must be an object with a 'services' array.")

    entries: list[CatalogueEntry] = []
    for index, row in enumerate(raw["services"]):
        entries.append(_parse_entry(row, index))
    return entries


def _parse_entry(row: Any, index: int) -> CatalogueEntry:
    if not isinstance(row, dict):
        raise SeedError(f"services[{index}] is not an object.")

    def required(field: str) -> str:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise SeedError(f"services[{index}].{field} must be a non-empty string.")
        return value.strip()

    service_type = required("type")
    if service_type not in _ALLOWED_TYPES:
        raise SeedError(
            f"services[{index}].type must be one of {_ALLOWED_TYPES}, got {service_type!r}."
        )

    status = required("status")
    if status not in _ALLOWED_STATUSES:
        raise SeedError(
            f"services[{index}].status must be one of {_ALLOWED_STATUSES}, got {status!r}."
        )

    name = required("name")
    if len(name) > _MAX_NAME_LENGTH:
        raise SeedError(
            f"services[{index}].name exceeds {_MAX_NAME_LENGTH} characters (schema.md)."
        )

    aliases_raw = row.get("aliases", [])
    if not isinstance(aliases_raw, list) or any(not isinstance(a, str) for a in aliases_raw):
        raise SeedError(f"services[{index}].aliases must be an array of strings.")

    known_amount = row.get("known_amount")
    if known_amount is not None and (
        not isinstance(known_amount, int) or isinstance(known_amount, bool) or known_amount < 0
    ):
        raise SeedError(
            f"services[{index}].known_amount must be null or a non-negative integer (minor units)."
        )

    return CatalogueEntry(
        type=service_type,
        name=name,
        collecting_body=required("collecting_body"),
        category=required("category"),
        aliases=tuple(alias.strip() for alias in aliases_raw if alias.strip()),
        known_amount=known_amount,
        currency=required("currency"),
        status=status,
    )


def _natural_key(name: str, collecting_body: str) -> tuple[str, str]:
    """Stable identity for a catalogue row: name + collecting body, case-insensitive."""
    return (name.strip().casefold(), collecting_body.strip().casefold())


def _index_existing(db: Session) -> dict[tuple[str, str], Service]:
    existing: dict[tuple[str, str], Service] = {}
    for service in db.execute(select(Service)).scalars():
        existing[_natural_key(service.name, service.collecting_body)] = service
    return existing


def seed_catalogue(
    db: Session,
    entries: list[CatalogueEntry],
    *,
    dry_run: bool = False,
) -> SeedResult:
    """Upsert the catalogue by natural key, reporting created/updated/skipped.

    A row whose fields already match the store is *skipped* (counted, not
    written), so a re-run produces ``created=0`` and does not churn rows. With
    ``dry_run`` the counts are computed from the store's current state and nothing
    is written or flushed.
    """
    existing = _index_existing(db)

    created = updated = skipped = 0
    seen: set[tuple[str, str]] = set()

    for entry in entries:
        key = _natural_key(entry.name, entry.collecting_body)
        if key in seen:
            raise SeedError(
                "Catalogue data file has two rows with the same name and "
                f"collecting body: {entry.name!r} / {entry.collecting_body!r}."
            )
        seen.add(key)

        service = existing.get(key)
        if service is None:
            created += 1
            if not dry_run:
                db.add(_build_service(entry))
            continue

        if _is_unchanged(service, entry):
            skipped += 1
            continue

        updated += 1
        if not dry_run:
            _apply(service, entry)

    if not dry_run and (created or updated):
        db.flush()

    return SeedResult(
        created=created,
        updated=updated,
        skipped=skipped,
        total=len(entries),
    )


def _build_service(entry: CatalogueEntry) -> Service:
    return Service(
        type=entry.type,
        name=entry.name,
        collecting_body=entry.collecting_body,
        category=entry.category,
        aliases=list(entry.aliases),
        known_amount=entry.known_amount,
        currency=entry.currency,
        status=entry.status,
    )


def _is_unchanged(service: Service, entry: CatalogueEntry) -> bool:
    return (
        service.type == entry.type
        and service.category == entry.category
        and list(service.aliases or []) == list(entry.aliases)
        and service.known_amount == entry.known_amount
        and service.currency == entry.currency
        and service.status == entry.status
    )


def _apply(service: Service, entry: CatalogueEntry) -> None:
    service.type = entry.type
    service.category = entry.category
    service.aliases = list(entry.aliases)
    service.known_amount = entry.known_amount
    service.currency = entry.currency
    service.status = entry.status


def load_catalogue(
    db: Session,
    path: Path | str = DEFAULT_CATALOGUE_PATH,
    *,
    dry_run: bool = False,
) -> SeedResult:
    """Convenience: read ``path`` and upsert it into ``db``."""
    return seed_catalogue(db, load_entries(path), dry_run=dry_run)
