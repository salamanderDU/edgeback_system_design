from __future__ import annotations

from dataclasses import dataclass

from edgeback.config.models import ExecutionConfig
from edgeback.domain import Side


@dataclass(frozen=True, slots=True)
class CostDecomposition:
    base_price: float
    spread_cost_usd: float
    slippage_cost_usd: float
    commission_usd: float
    effective_price: float
    model_ids: dict[str, str]

    @property
    def total_cost_usd(self) -> float:
        return self.spread_cost_usd + self.slippage_cost_usd + self.commission_usd


class ExecutionCosts:
    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config

    def estimate_round_trip_per_share(self, reference_price: float) -> float:
        per_side = self.decompose(reference_price, 1, Side.BUY)
        other_side = self.decompose(reference_price, 1, Side.SELL)
        return per_side.total_cost_usd + other_side.total_cost_usd

    def decompose(
        self,
        base_price: float,
        quantity: int,
        side: Side,
        *,
        limit_price: float | None = None,
    ) -> CostDecomposition:
        if base_price <= 0 or quantity <= 0:
            raise ValueError("base_price and quantity must be positive")
        multiplier = self.config.cost_multiplier
        spread_bps = (
            self.config.spread.full_spread_bps / 2.0
            if self.config.spread.model == "fixed_bps"
            else 0.0
        )
        slippage_bps = (
            self.config.slippage.bps_per_side
            if self.config.slippage.model == "fixed_bps"
            else 0.0
        )
        spread = base_price * quantity * spread_bps / 10_000.0 * multiplier
        slippage = base_price * quantity * slippage_bps / 10_000.0 * multiplier

        # A limit fill may never have a worse execution price than its limit. Commission is separate.
        if limit_price is not None:
            max_price_cost = (
                max(0.0, (limit_price - base_price) * quantity)
                if side is Side.BUY
                else max(0.0, (base_price - limit_price) * quantity)
            )
            price_cost = spread + slippage
            if price_cost > max_price_cost:
                if price_cost > 0:
                    ratio = max_price_cost / price_cost
                    spread *= ratio
                    slippage *= ratio
                else:
                    spread = slippage = 0.0

        commission_cfg = self.config.commission
        if commission_cfg.model == "zero":
            commission = 0.0
        elif commission_cfg.model == "fixed_per_order":
            commission = commission_cfg.usd_per_order
        elif commission_cfg.model == "per_share":
            commission = max(
                quantity * commission_cfg.usd_per_share,
                commission_cfg.minimum_usd_per_order,
            )
        elif commission_cfg.model == "bps":
            commission = base_price * quantity * commission_cfg.bps_of_notional / 10_000.0
        else:  # pragma: no cover - Pydantic prevents this
            raise ValueError(f"Unknown commission model: {commission_cfg.model}")
        commission *= multiplier
        price_cost_per_share = (spread + slippage) / quantity
        effective = base_price + side.sign * price_cost_per_share
        return CostDecomposition(
            base_price=base_price,
            spread_cost_usd=round(spread, 10),
            slippage_cost_usd=round(slippage, 10),
            commission_usd=round(commission, 10),
            effective_price=round(effective, 10),
            model_ids={
                "spread": self.config.spread.model,
                "slippage": self.config.slippage.model,
                "commission": commission_cfg.model,
                "cost_multiplier": str(multiplier),
            },
        )
