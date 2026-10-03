"""Make the payment module importable when run from the API test command."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

# Fixtures for the FEAT-005 authorisation surface live in their own module so
# other payment tests can add fixtures without conflicting here.
pytest_plugins = ["payment_fixtures"]
