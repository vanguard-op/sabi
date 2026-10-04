"""Load the version-controlled service catalogue into the primary store.

Run from ``services/api`` with the API's virtualenv active and the environment
loaded:

    python -m scripts.seed_catalogue --file data/catalogue.json [--dry-run]

The catalogue is public, non-secret data (real Nigerian services and the
organisations that collect for them), and a hosted staging load is intended, so
this entrypoint deliberately carries no development-only guard: the data is safe
wherever the primary store is writable, and refusing in staging would defeat the
point of a reproducible seed (D-048). Contrast ``seed_dev_staff``, which guards
``ENVIRONMENT=development`` because it writes a credential and a factor. Provide
``DATABASE_URL`` for the target store; the standard environment configuration
supplies it.

``--dry-run`` reports the created/updated/skipped counts without writing.
Idempotent: rows are upserted by ``name + collecting_body`` and a re-run creates
nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python -m scripts.seed_catalogue` from the service root without an
# editable install on the path.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.catalogue.seed import DEFAULT_CATALOGUE_PATH, SeedError, load_catalogue  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import build_session_factory  # noqa: E402


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_catalogue",
        description="Load the Nigerian service catalogue into the primary store.",
    )
    parser.add_argument(
        "--file",
        default=str(DEFAULT_CATALOGUE_PATH),
        help="Path to the catalogue JSON file (default: the version-controlled data file).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the store.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    session_factory = build_session_factory(settings)

    try:
        with session_factory() as db:
            result = load_catalogue(db, args.file, dry_run=args.dry_run)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
    except SeedError as exc:
        print(f"Refusing to seed the catalogue: {exc}", file=sys.stderr)
        return 2

    prefix = "Dry run: would load" if args.dry_run else "Loaded"
    print(f"{prefix} {result.total} services.")
    print(f"  Created: {result.created}")
    print(f"  Updated: {result.updated}")
    print(f"  Unchanged (skipped): {result.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
