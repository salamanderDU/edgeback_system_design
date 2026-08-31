"""
Shared-capital allocation of simultaneous intents (T450, docs/02 §7).

When several symbols emit intents at the same ``bar_end_utc`` they compete for
one portfolio's cash and gross-exposure headroom. The allocator evaluates the
batch deterministically: candidates are ordered by
``(priority descending, canonical symbol ascending, creation order)`` and each
intent is evaluated by the risk manager against a **projected** portfolio state
that reserves the notional of intents already accepted earlier in the same
batch. This makes the accepted set independent of the order in which the engine
dispatched ``on_bar`` callbacks (ADR-013).

The MVP allocator is ``priority_then_symbol`` (docs/02 §7). Future allocators
(such as ``pro_rata``) can be added behind :class:`IntentAllocator`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from edgeback.domain.orders import OrderIntent
from edgeback.risk import RiskContext, RiskDecision, RiskManager

__all__ = [
    "AllocationContext",
    "IntentAllocator",
    "PriorityThenSymbolAllocator",
    "build_allocator",
]


@dataclass(frozen=True)
class AllocationContext:
    """
    One timestamp's batch of simultaneous intents plus the pre-reservation
    portfolio state used by the risk manager.
    """

    intents: tuple[OrderIntent, ...]
    risk: RiskManager
    ctx: RiskContext


class IntentAllocator(Protocol):
    """Deterministic allocator interface for simultaneous entry intents."""

    def allocate(self, allocation_ctx: AllocationContext) -> list[RiskDecision]:
        """
        Return one :class:`RiskDecision` per intent, preserving the order of
        ``allocation_ctx.intents``.
        """
        ...


class PriorityThenSymbolAllocator:
    """
    docs/02 §7 MVP allocator.

    Orders candidates by ``(-priority, canonical symbol, creation order)`` and
    evaluates each intent against a projected ``cash`` / ``gross_exposure``
    that deducts the notional of intents accepted earlier in the same batch.
    The risk manager still rejects intents on lockouts, sizing, per-position
    caps, volume participation, duplicate orders, and exposure/cash limits;
    those decisions are recorded exactly like single-symbol runs (NFR-004).
    """

    def allocate(self, allocation_ctx: AllocationContext) -> list[RiskDecision]:
        intents = allocation_ctx.intents
        # Enumerated in engine emission order (canonical-symbol dispatch order);
        # sorting by (-priority, symbol, index) removes dependence on emission
        # history beyond the documented tie-breakers.
        indexed = sorted(
            enumerate(intents),
            key=lambda pair: (-pair[1].priority, pair[1].symbol, pair[0]),
        )

        projected_cash = allocation_ctx.ctx.cash
        projected_gross = allocation_ctx.ctx.gross_exposure
        decisions: dict[int, RiskDecision] = {}

        for idx, intent in indexed:
            projected_ctx = replace(
                allocation_ctx.ctx,
                cash=projected_cash,
                gross_exposure=projected_gross,
            )
            decision = allocation_ctx.risk.evaluate(intent, projected_ctx)
            decisions[idx] = decision
            if decision.accepted and decision.order is not None:
                price = allocation_ctx.ctx.reference_prices.get(intent.symbol, 0.0)
                reserved = decision.order.shares * price
                projected_cash -= reserved
                projected_gross += float(reserved)

        return [decisions[i] for i in range(len(intents))]


def build_allocator(name: str) -> IntentAllocator:
    """Build the configured entry allocator; fail fast on unknown names."""
    if name != "priority_then_symbol":
        raise ValueError(f"unknown entry_allocation {name!r}; supported: priority_then_symbol")
    return PriorityThenSymbolAllocator()
