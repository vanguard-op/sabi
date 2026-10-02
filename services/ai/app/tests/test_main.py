"""The serving entrypoint boots and registers feature routers under /v1."""

from __future__ import annotations

from types import ModuleType

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import main as app_main
from core.config import ModelSettings


def _stub_feature_module(name: str) -> ModuleType:
    module = ModuleType(f"{name}.router")
    router = APIRouter()

    @router.get("/agent/intents")
    def intents() -> dict[str, str]:  # pragma: no cover - route body
        return {"source": "model"}

    module.router = router
    return module


def _importer(missing: tuple[str, ...], *, stub: str | None = None):
    def import_module(path: str) -> ModuleType:
        if stub is not None and path == f"{stub}.router":
            return _stub_feature_module(stub)
        if path in missing:
            raise ModuleNotFoundError(f"No module named '{path}'", name=path)
        raise AssertionError(f"unexpected import: {path}")

    return import_module


def test_health_is_dependency_free() -> None:
    client = TestClient(app_main.create_app())
    assert client.get("/health").json() == {"status": "ok"}


def test_app_boots_when_no_feature_router_has_landed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app_main.importlib,
        "import_module",
        _importer(("intent.router", "ranking.router", "composition.router")),
    )
    app = app_main.create_app()
    assert not any(path.startswith("/v1") for path in app.openapi()["paths"])
    assert TestClient(app).get("/health").status_code == 200


def test_feature_router_is_mounted_under_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app_main.importlib,
        "import_module",
        _importer(("ranking.router", "composition.router"), stub="intent"),
    )
    client = TestClient(app_main.create_app())
    response = client.get("/v1/agent/intents")
    assert response.status_code == 200
    assert response.json() == {"source": "model"}


def test_module_without_router_is_a_wiring_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("intent.router")  # exists, but exposes no APIRouter
    monkeypatch.setattr(app_main.importlib, "import_module", lambda path: module)
    with pytest.raises(TypeError):
        app_main.load_feature_router("intent")


def test_settings_are_exposed_on_app_state() -> None:
    app = app_main.create_app()
    settings = app.state.settings
    assert isinstance(settings, ModelSettings)
    assert settings.primary_model_id == ModelSettings().primary_model_id
