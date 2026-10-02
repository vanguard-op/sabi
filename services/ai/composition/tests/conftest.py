"""Make ``services/ai`` importable as the package root for composition tests."""

from __future__ import annotations

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

from core.testing import FakeModelProvider  # noqa: E402


def build_test_client(responses=None, *, responder=None):
    """Build a TestClient with the model mocked out.

    The serving layer is stored on ``app.state`` so the endpoint never reaches
    for a real provider or the network.
    """

    from fastapi.testclient import TestClient

    from app.main import create_app
    from composition.dependencies import build_serving
    from core.config import ModelSettings

    app = create_app(ModelSettings(api_key="test-key"))
    provider = FakeModelProvider(responses, responder=responder)
    app.state.serving = build_serving(ModelSettings(api_key="test-key"), provider=provider)
    return TestClient(app), provider
