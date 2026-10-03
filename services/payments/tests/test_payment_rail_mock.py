"""Sandbox rail adapter: outcomes, idempotency, and backend selection (FEAT-005).

The mock rail stands in for the licensed partner while it is deferred (D-027).
Its value is that it reproduces the documented rail outcomes against the real
adapter, so these tests pin the behaviour the execution path depends on rather
than a bespoke double.
"""

from __future__ import annotations

from sabi_payments.core.rail import DisabledRail, RailCharge
from sabi_payments.rail import MockRail, MockScenario
from sabi_payments.rail.factory import build_rail
from sabi_payments.rail.settings import RailSettings


def charge(**overrides: object) -> RailCharge:
    fields: dict = {
        "payment_id": "pay-1",
        "user_id": "user-1",
        "amount": 50_000,
        "currency": "NGN",
        "payee": "Lagos State Internal Revenue",
        "payee_reference": "TIN-123",
        "payment_method_id": None,
        "idempotency_key": "exec-1",
    }
    fields.update(overrides)
    return RailCharge(**fields)  # type: ignore[arg-type]


def test_success_returns_a_reference_and_records_the_charge() -> None:
    rail = MockRail()
    outcome = rail.charge(charge())
    assert outcome.status == "succeeded"
    assert outcome.reference
    assert outcome.failure_reason is None
    assert len(rail.charges) == 1


def test_same_idempotency_key_yields_the_same_reference() -> None:
    rail = MockRail()
    first = rail.charge(charge())
    second = rail.charge(charge())
    assert first.reference == second.reference


def test_a_different_key_yields_a_different_reference() -> None:
    rail = MockRail()
    first = rail.charge(charge(idempotency_key="exec-1"))
    second = rail.charge(charge(idempotency_key="exec-2"))
    assert first.reference != second.reference


def test_decline_fails_with_a_reason_and_no_reference() -> None:
    rail = MockRail(MockScenario.DECLINE)
    outcome = rail.charge(charge())
    assert outcome.status == "failed"
    assert outcome.reference is None
    assert outcome.failure_reason


def test_insufficient_funds_is_a_refusal_the_service_maps_to_402() -> None:
    rail = MockRail(MockScenario.INSUFFICIENT_FUNDS)
    outcome = rail.charge(charge())
    assert outcome.status == "failed"
    # The service recognises a funding refusal by this wording (core rule).
    assert "insufficient" in (outcome.failure_reason or "").lower()


def test_unknown_outcome_is_pending_not_a_retry() -> None:
    rail = MockRail(MockScenario.UNKNOWN)
    outcome = rail.charge(charge())
    assert outcome.status == "pending"
    assert outcome.reference is None


def test_enqueue_overrides_one_charge_then_falls_back() -> None:
    rail = MockRail()
    rail.enqueue(MockScenario.UNKNOWN)
    assert rail.charge(charge()).status == "pending"
    assert rail.charge(charge()).status == "succeeded"


def test_non_positive_amount_is_never_acknowledged() -> None:
    rail = MockRail()
    outcome = rail.charge(charge(amount=0))
    assert outcome.status == "failed"
    assert outcome.reference is None


def test_health_reports_liveness_for_the_authorization_probe() -> None:
    assert MockRail().health() == "healthy"


def test_auto_selects_mock_in_development() -> None:
    rail = build_rail(RailSettings(_env_file=None, environment="development"))
    assert isinstance(rail, MockRail)


def test_auto_selects_disabled_outside_development() -> None:
    for environment in ("staging", "production"):
        rail = build_rail(RailSettings(_env_file=None, environment=environment))  # type: ignore[arg-type]
        assert isinstance(rail, DisabledRail)


def test_explicit_backends_are_honoured() -> None:
    assert isinstance(
        build_rail(RailSettings(_env_file=None, backend="mock", environment="production")),
        MockRail,
    )
    assert isinstance(
        build_rail(RailSettings(_env_file=None, backend="disabled", environment="development")),
        DisabledRail,
    )


def test_disabled_rail_reports_pending_and_invents_no_reference() -> None:
    outcome = DisabledRail().charge(charge())
    assert outcome.status == "pending"
    assert outcome.reference is None


def test_configured_scenario_and_prefix_reach_the_adapter() -> None:
    rail = build_rail(
        RailSettings(
            _env_file=None,
            backend="mock",
            mock_default_scenario="decline",
            mock_reference_prefix="SANDBOX",
        )
    )
    assert isinstance(rail, MockRail)
    assert rail.default_scenario is MockScenario.DECLINE
    assert rail.charge(charge()).status == "failed"


def test_auto_never_selects_the_mock_outside_development(monkeypatch) -> None:
    """A simulated settled charge outside development would tell a user an
    obligation was paid when no money moved. The environment must be read from
    the app-wide ENVIRONMENT variable, not a rail_-prefixed one, or it silently
    defaults to development."""
    from sabi_payments.rail.settings import RailSettings

    for env in ("staging", "production"):
        monkeypatch.setenv("ENVIRONMENT", env)
        monkeypatch.delenv("RAIL_BACKEND", raising=False)
        assert RailSettings().resolved_backend() == "disabled", env

    monkeypatch.setenv("ENVIRONMENT", "development")
    assert RailSettings().resolved_backend() == "mock"
