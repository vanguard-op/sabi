"""Unit tests for router auto-discovery in the app factory.

The discovery guard decides whether a module mounts under /v1. A module that has
not landed yet (its package directory is absent) is skipped so the monolith can
boot; a package that is present but whose router cannot be imported must fail
the boot rather than silently disappear. The guard takes its module list and its
import seams by argument, so every branch is exercised without real packages.
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI

from app.main import MODULE_NAMES, ROUTERLESS_MODULES, _include_module_routers


def _present(name: str):
    """A find_spec double that reports exactly ``name`` as present."""
    return lambda path: object() if path == name else None


def _importer(*, result=None, error: BaseException | None = None):
    def _import(path: str):  # type: ignore[no-untyped-def]
        if error is not None:
            raise error
        return result

    return _import


def _module_with_router(path: str = "/ping") -> ModuleType:
    module = ModuleType("app.fake.router")
    module.router = APIRouter()

    @module.router.get(path)
    def _ping() -> dict[str, str]:  # pragma: no cover - route body is unused
        return {"status": "ok"}

    return module


def test_a_package_that_has_not_landed_is_skipped() -> None:
    app = FastAPI()
    _include_module_routers(
        app,
        module_names=["future"],
        find_spec=lambda path: None,
        import_module=_importer(result=_module_with_router()),
    )
    assert app.openapi()["paths"] == {}


def test_a_landed_module_mounts_under_v1() -> None:
    app = FastAPI()
    _include_module_routers(
        app,
        module_names=["fake"],
        find_spec=_present("app.fake"),
        import_module=_importer(result=_module_with_router()),
    )
    assert "/v1/ping" in app.openapi()["paths"]


def test_a_landed_router_that_fails_to_import_raises() -> None:
    # The package is present, but importing its router hits a missing
    # dependency. That is a real fault, not an absent module.
    app = FastAPI()
    error = ModuleNotFoundError("No module named 'some_installed_dep'")
    error.name = "some_installed_dep"
    with pytest.raises(ModuleNotFoundError):
        _include_module_routers(
            app,
            module_names=["fake"],
            find_spec=_present("app.fake"),
            import_module=_importer(error=error),
        )


def test_a_landed_package_missing_its_router_raises() -> None:
    # The package landed but declares no router and is not declared routerless:
    # the module must surface rather than boot without its routes.
    app = FastAPI()
    error = ModuleNotFoundError("No module named 'app.fake.router'")
    error.name = "app.fake.router"
    with pytest.raises(ModuleNotFoundError):
        _include_module_routers(
            app,
            module_names=["fake"],
            find_spec=_present("app.fake"),
            import_module=_importer(error=error),
        )


def test_a_declared_routerless_package_is_skipped() -> None:
    app = FastAPI()
    error = ModuleNotFoundError("No module named 'app.jobs.router'")
    error.name = "app.jobs.router"
    _include_module_routers(
        app,
        module_names=["jobs"],
        routerless=frozenset({"jobs"}),
        find_spec=_present("app.jobs"),
        import_module=_importer(error=error),
    )
    assert app.openapi()["paths"] == {}


def test_a_module_without_a_router_attribute_raises() -> None:
    app = FastAPI()
    with pytest.raises(RuntimeError, match="defines no `router`"):
        _include_module_routers(
            app,
            module_names=["fake"],
            find_spec=_present("app.fake"),
            import_module=_importer(result=SimpleNamespace()),
        )


def test_a_missing_parent_package_is_treated_as_not_landed() -> None:
    app = FastAPI()

    def _find(path: str):
        raise ModuleNotFoundError("No module named 'app.fake'")

    _include_module_routers(
        app,
        module_names=["fake.sub"],
        find_spec=_find,
        import_module=_importer(result=_module_with_router()),
    )
    assert app.openapi()["paths"] == {}


def test_the_real_inventory_keeps_routerless_modules_out_of_the_http_surface() -> None:
    # Reconciliation is a scheduler-facing job layer: it is part of the
    # inventory, but every module that mounts routes must have a router.
    assert "reconciliation" in MODULE_NAMES
    assert ROUTERLESS_MODULES == frozenset({"reconciliation"})
