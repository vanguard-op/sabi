"""Unit tests for the catalogue seeder (FEAT-004, FEAT-012; D-048).

Covers the properties the seeder exists to guarantee: the seed is idempotent,
distinct networks and DISCOs stay distinct rows, missing amounts are never
invented, and a loaded catalogue makes discovery return the right row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.catalogue.search import rank
from app.catalogue.seed import (
    CatalogueEntry,
    SeedError,
    load_catalogue,
    load_entries,
    seed_catalogue,
)
from app.db.base import Base
from app.db.models import Service


def _case_insensitive_unique_index(engine) -> None:
    """SQLite does not implement ``lower(col)`` expression indexes by default, so
    install a minimal equivalent on the connection the test will use. This makes
    SQLite reject a duplicate case-folded natural key, mirroring the Postgres
    unique expression index the migration applies.
    """

    def create(conn, _record) -> None:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='services'"
        ).fetchone()
        if exists:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_services_natural_key "
                "ON services (lower(name), lower(collecting_body))"
            )

    event.listen(engine, "connect", create)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _entry(**overrides: object) -> CatalogueEntry:
    values: dict[str, object] = {
        "type": "biller",
        "name": "MTN Airtime",
        "collecting_body": "MTN Nigeria",
        "category": "airtime",
        "aliases": ("MTN",),
        "known_amount": None,
        "currency": "NGN",
        "status": "active",
    }
    values.update(overrides)
    return CatalogueEntry(**values)  # type: ignore[arg-type]


def _build(name: str, collecting_body: str) -> Service:
    return Service(
        type="biller",
        name=name,
        collecting_body=collecting_body,
        category="airtime",
        aliases=[],
        known_amount=None,
        currency="NGN",
        status="active",
    )


# --- data file --------------------------------------------------------------


def test_shipped_data_file_loads_the_expected_catalogue() -> None:
    entries = load_entries()

    # Ten DISCOs, four separate airtime services, four separate data services,
    # and a set of government levies/taxes.
    names = {entry.name for entry in entries}
    for disco in (
        "Ikeja Electric (IE)",
        "Eko Electricity Distribution Company (EKEDC)",
        "Abuja Electricity Distribution Company (AEDC)",
        "Kano Electricity Distribution Company (KEDCO)",
        "Port Harcourt Electricity Distribution Company (PHED)",
        "Enugu Electricity Distribution Company (EEDC)",
        "Kaduna Electric (KAEDC)",
        "Jos Electricity Distribution Company (JED)",
        "Ibadan Electricity Distribution Company (IBEDC)",
        "Benin Electricity Distribution Company (BEDC)",
    ):
        assert disco in names

    for network in ("MTN", "Airtel", "Glo", "9mobile"):
        assert f"{network} Airtime" in names
        assert f"{network} Data" in names

    assert all(entry.currency == "NGN" for entry in entries)
    assert all(entry.status == "active" for entry in entries)
    assert all(entry.known_amount is None for entry in entries)
    assert any(entry.type == "government" for entry in entries)


def test_shipped_catalogue_keeps_networks_and_discos_distinct() -> None:
    entries = load_entries()

    airtime = [entry for entry in entries if entry.category == "airtime"]
    data = [entry for entry in entries if entry.category == "data"]
    # Two networks are never merged into one row.
    assert len({entry.collecting_body for entry in airtime}) == 4
    assert len({entry.collecting_body for entry in data}) == 4
    # Every airtime row is a distinct service, and networks are not two DISCOs.
    assert len({(entry.name, entry.collecting_body) for entry in entries}) == len(entries)


def test_government_rows_carry_an_agency_as_collecting_body() -> None:
    entries = load_entries()
    government = [entry for entry in entries if entry.type == "government"]
    assert government
    assert all(entry.collecting_body for entry in government)


# --- idempotency ------------------------------------------------------------


def test_seed_is_idempotent_on_the_natural_key(db: Session) -> None:
    entries = load_entries()

    first = seed_catalogue(db, entries)
    db.commit()
    second = seed_catalogue(db, entries)
    db.commit()

    assert first.created == len(entries)
    assert first.updated == 0
    assert second.created == 0
    assert second.updated == 0
    assert second.skipped == len(entries)

    rows = db.query(Service).all()
    assert len(rows) == len(entries)


def test_natural_key_is_case_insensitive(db: Session) -> None:
    seed_catalogue(db, [_entry(name="Airtel Airtime", collecting_body="Airtel Nigeria")])
    db.commit()

    # A differently-cased duplicate must update the same row, not add one.
    result = seed_catalogue(
        db,
        [_entry(name="airtel airtime", collecting_body="AIRTEL NIGERIA", category="data")],
    )
    db.commit()

    assert result.created == 0
    assert result.updated == 1
    assert db.query(Service).count() == 1
    assert db.query(Service).one().category == "data"


def test_updated_row_refreshes_the_stored_fields(db: Session) -> None:
    seed_catalogue(db, [_entry(aliases=("MTN",))])
    db.commit()

    seed_catalogue(
        db,
        [_entry(aliases=("MTN", "MTN recharge"), known_amount=None, status="unavailable")],
    )
    db.commit()

    stored = db.query(Service).one()
    assert stored.aliases == ["MTN", "MTN recharge"]
    assert stored.status == "unavailable"


def test_dry_run_reports_without_writing(db: Session) -> None:
    result = load_catalogue(db, dry_run=True)

    assert result.created == result.total
    assert result.total > 0
    assert db.query(Service).count() == 0


def test_dry_run_over_a_loaded_store_reports_no_writes(db: Session) -> None:
    load_catalogue(db)
    db.commit()

    result = load_catalogue(db, dry_run=True)

    assert result.created == 0
    assert result.updated == 0
    assert result.skipped == result.total
    assert db.query(Service).count() == result.total


def test_known_amount_is_never_invented(db: Session) -> None:
    entries = load_entries()
    seed_catalogue(db, entries)
    db.commit()

    assert all(row.known_amount is None for row in db.query(Service).all())


# --- natural-key uniqueness (database level) --------------------------------


@pytest.fixture
def constrained_db() -> Session:
    """A store with the case-insensitive natural-key uniqueness applied."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _case_insensitive_unique_index(engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_duplicate_natural_key_insert_is_rejected(constrained_db: Session) -> None:
    constrained_db.add(_build("MTN Airtime", "MTN Nigeria"))
    constrained_db.commit()

    constrained_db.add(_build("MTN Airtime", "MTN Nigeria"))
    with pytest.raises(IntegrityError):
        constrained_db.commit()


def test_duplicate_natural_key_is_rejected_case_insensitively(constrained_db: Session) -> None:
    constrained_db.add(_build("MTN Airtime", "MTN Nigeria"))
    constrained_db.commit()

    constrained_db.add(_build("mtn airtime", "MTN NIGERIA"))
    with pytest.raises(IntegrityError):
        constrained_db.commit()


def test_distinct_natural_keys_both_persist(constrained_db: Session) -> None:
    constrained_db.add(_build("MTN Airtime", "MTN Nigeria"))
    constrained_db.add(_build("Airtel Airtime", "Airtel Nigeria"))
    constrained_db.commit()
    assert constrained_db.query(Service).count() == 2


def test_model_declares_the_case_insensitive_natural_key() -> None:
    # The model carries the same unique expression index the migration creates,
    # so an Alembic compare does not drift from the store.
    table = Base.metadata.tables["services"]
    natural_key = next(
        (index for index in table.indexes if index.name == "uq_services_natural_key"),
        None,
    )
    assert natural_key is not None and natural_key.unique
    rendered = str(natural_key.expressions[0])
    assert "lower" in rendered and "name" in rendered
    assert "collecting_body" in str(natural_key.expressions[1])


# --- validation -------------------------------------------------------------


def test_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SeedError):
        load_entries(tmp_path / "absent.json")


def test_invalid_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "catalogue.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SeedError):
        load_entries(path)


def test_row_with_a_bad_type_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "catalogue.json"
    path.write_text(
        json.dumps(
            {
                "services": [
                    {
                        "type": "utility",
                        "name": "X",
                        "collecting_body": "Y",
                        "category": "z",
                        "aliases": [],
                        "known_amount": None,
                        "currency": "NGN",
                        "status": "active",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SeedError):
        load_entries(path)


def test_file_with_duplicate_natural_keys_is_refused(db: Session) -> None:
    duplicate = _entry()
    with pytest.raises(SeedError):
        seed_catalogue(db, [duplicate, duplicate])


# --- discovery integration --------------------------------------------------


def test_loaded_catalogue_ranks_the_right_rows(db: Session) -> None:
    entries = load_entries()
    seed_catalogue(db, entries)
    db.commit()

    services = list(db.execute(select(Service)).scalars())

    airtel = rank(services, "airtel", 5)
    assert airtel and airtel[0][0].name == "Airtel Airtime"
    # MTN must never be substituted for an Airtel request (D-047).
    assert all(row.name != "MTN Airtime" for row, _ in airtel)

    ikeja = rank(services, "ikeja", 5)
    assert ikeja and ikeja[0][0].name == "Ikeja Electric (IE)"
    assert ikeja[0][0].collecting_body == "Ikeja Electricity Distribution Company"

    levy = rank(services, "levy", 5)
    assert levy
    assert all(row[0].category == "levy" for row in levy)

    assert rank(services, "value added tax", 5)[0][0].collecting_body == (
        "Federal Inland Revenue Service"
    )
