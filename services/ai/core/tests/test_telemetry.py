from __future__ import annotations

from decimal import Decimal

from core.config import FLASH_MODEL_ID, PRIMARY_MODEL_ID, Capability
from core.provider import ModelUsage
from core.telemetry import CostTracker, TaskCost, estimate_cost


def test_cost_uses_the_pinned_list_price():
    cost = estimate_cost(
        FLASH_MODEL_ID, ModelUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    )
    assert cost == Decimal("3.50")


def test_unknown_model_is_priced_at_zero():
    assert estimate_cost("unknown-model", ModelUsage(input_tokens=100, output_tokens=100)) == 0


def test_task_cost_accumulates_calls_and_checks_the_ceiling():
    task = CostTracker().begin(Capability.INTENT_RESOLUTION, model_id=FLASH_MODEL_ID)
    task.record(ModelUsage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert task.calls == 1
    assert task.within_ceiling is False  # 3.50 USD exceeds the 0.02 ceiling


def test_small_task_stays_within_ceiling():
    task = TaskCost(capability=Capability.DISCOVERY_RANKING, model_id=FLASH_MODEL_ID)
    task.record(ModelUsage(input_tokens=1_000, output_tokens=500))
    assert task.within_ceiling is True
    assert task.calls == 1


def test_task_cost_mapping_is_serialisable():
    task = CostTracker().begin(Capability.INTERFACE_COMPOSITION, model_id=PRIMARY_MODEL_ID)
    task.record(ModelUsage(input_tokens=1000, output_tokens=200))
    mapping = task.to_mapping()
    assert mapping["capability"] == "interface_composition"
    assert mapping["within_ceiling"] is True
