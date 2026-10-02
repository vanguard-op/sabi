"""Model cost telemetry and ceiling checks (NFR-050 to NFR-052).

Cost is measured per completed user task, not per model call, so a tracker is opened
once for a task and records every provider call the task makes, including retries and
clarification turns. The crate is compared against the capability's ceiling before the
task is considered done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from core.config import COST_CEILINGS, MODEL_PRICES, Capability, ModelPrice
from core.provider import ModelUsage

_USD_CENTS = Decimal("0.000001")


def price_for(model_id: str) -> ModelPrice | None:
    return MODEL_PRICES.get(model_id)


def estimate_cost(model_id: str, usage: ModelUsage) -> Decimal:
    """Return the list-price cost in USD for one call, or zero if unpriced."""

    price = price_for(model_id)
    if price is None:
        return Decimal("0")
    cost = (
        Decimal(usage.input_tokens) * price.input_per_million
        + Decimal(usage.output_tokens) * price.output_per_million
    ) / Decimal(1_000_000)
    return cost.quantize(_USD_CENTS, rounding=ROUND_HALF_UP)


@dataclass
class TaskCost:
    """Accumulated cost for one completed user task."""

    capability: Capability
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    usd: Decimal = Decimal("0")

    def record(self, usage: ModelUsage, *, model_id: str | None = None) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.calls += 1
        self.usd += estimate_cost(model_id or self.model_id, usage)
        self.usd = self.usd.quantize(_USD_CENTS, rounding=ROUND_HALF_UP)

    @property
    def ceiling(self) -> Decimal:
        return COST_CEILINGS[self.capability].usd

    @property
    def within_ceiling(self) -> bool:
        return self.usd <= self.ceiling

    def to_mapping(self) -> dict[str, object]:
        return {
            "capability": self.capability.value,
            "model_id": self.model_id,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "usd": str(self.usd),
            "ceiling_usd": str(self.ceiling),
            "within_ceiling": self.within_ceiling,
        }


@dataclass
class CostTracker:
    """Opens a :class:`TaskCost` per completed task."""

    _tasks: list[TaskCost] = field(default_factory=list)

    def begin(self, capability: Capability, *, model_id: str) -> TaskCost:
        task = TaskCost(capability=capability, model_id=model_id)
        self._tasks.append(task)
        return task

    @property
    def tasks(self) -> tuple[TaskCost, ...]:
        return tuple(self._tasks)
