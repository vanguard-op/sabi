"""Provision the development Operations Console administrator account.

Run from ``services/api`` with the API's virtualenv active and the environment
loaded (the Makefile's ``seed-dev-staff`` target does both):

    SABI_DEV_STAFF_PASSWORD='choose-a-local-password' \
        python scripts/seed_dev_staff.py

The password comes only from ``SABI_DEV_STAFF_PASSWORD`` and never appears in the
command line or the repository. The email defaults to ``admin@sabi.local``; set
``SABI_DEV_STAFF_EMAIL`` to provision under a different local identity.

The account is an administrator so every Phase 1 console surface is reachable
(provider review, health and quarantine, and the audit view). Provisioning
refuses to run unless ``ENVIRONMENT=development`` (NFR-024). The printed TOTP
secret is deliberate provisioning output for the authenticator app; the password
is never printed or logged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python scripts/seed_dev_staff.py` from the service root without an
# editable install on the path.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import build_session_factory  # noqa: E402
from app.staff.seed import (  # noqa: E402
    DEFAULT_DEV_STAFF_EMAIL,
    SeedError,
    seed_dev_staff,
)

PASSWORD_ENV = "SABI_DEV_STAFF_PASSWORD"
EMAIL_ENV = "SABI_DEV_STAFF_EMAIL"


def main() -> int:
    settings = get_settings()
    password = os.environ.get(PASSWORD_ENV, "")
    email = os.environ.get(EMAIL_ENV, DEFAULT_DEV_STAFF_EMAIL).strip() or DEFAULT_DEV_STAFF_EMAIL

    if not password:
        print(
            f"Set {PASSWORD_ENV} to the local staff password before running the seed.",
            file=sys.stderr,
        )
        return 2

    session_factory = build_session_factory(settings)
    try:
        with session_factory() as db:
            result = seed_dev_staff(db, settings, email=email, password=password)
            db.commit()
    except SeedError as exc:
        print(f"Refusing to seed: {exc}", file=sys.stderr)
        return 3

    action = "Created" if result.created else "Updated"
    print(f"{action} the development staff administrator.")
    print(f"  Email:    {result.email}")
    print(f"  Role:     {result.role}")
    print(f"  Password: (the value of {PASSWORD_ENV})")
    print("  TOTP secret (enrol this in an authenticator app now; it is shown once):")
    print(f"    {result.totp_secret}")
    print(f"  Current code: {result.current_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
