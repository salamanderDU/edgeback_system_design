"""
Execution cost models (T410).

Implements the documented cost decomposition from ``docs/04_BACKTEST_ENGINE.md`` §6:

    base execution price
    +/- synthetic half-spread
    +/- slippage
    + commission/fees
    = effective execution

Supported models:
- Spread: ``fixed_bps`` (half of the full spread applied adversely once per side).
- Slippage: ``fixed_bps`` (applied adversely per side).
- Commission: ``zero``, ``fixed_per_order``, ``per_share`` (with optional
  per-order minimum), or ``bps`` of trade notional.

All money values are rounded to cents via the shared ROUND_HALF_UP policy.
A :class:`CostDecomposition` records each component separately so fills can
carry ``spread_usd`` / ``slippage_usd`` / ``commission_usd`` for the portfolio
ledger. ``effective_price`` is the informational execution price including all
costs as a per-share adverse adjustment (matching T400's accounting module).

These models are pure and deterministic: they never perform I/O and depend
only on the resolved execution configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from edgeback.config.models import CommissionConfig, ExecutionConfig, SlippageConfig, SpreadConfig
from edgeback.portfolio.accounting import round_money

BASIS_POINTS_PER_UNIT = 10_000


def _bps_value(bps: float, base: float) -> float:
    """Convert a basis-point percentage to a proportionate value."""
    return bps / BASIS_POINTS_PER_UNIT * base


# ---------------------------------------------------------------------------
# Model protocols
# ---------------------------------------------------------------------------


class CommissionModel(Protocol):
    """Computes commission in USD for a fill."""

    model_id: str

    def compute(self, shares: int, notional_usd: float) -> float: ...


class SpreadModel(Protocol):
    """Computes adverse spread cost in USD for a fill."""

    model_id: str

    def compute(self, shares: int, notional_usd: float) -> float: ...


class SlippageModel(Protocol):
    """Computes adverse slippage cost in USD for a fill."""

    model_id: str

    def compute(self, shares: int, notional_usd: float) -> float: ...


# ---------------------------------------------------------------------------
# Commission implementations
# ---------------------------------------------------------------------------


class ZeroCommission:
    """No commission (``model: zero``)."""

    model_id = "zero"

    def compute(self, shares: int, notional_usd: float) -> float:
        return 0.0


class FixedPerOrderCommission:
    """Fixed USD commission charged once per order/fill (``model: fixed_per_order``)."""

    model_id = "fixed_per_order"

    def __init__(self, usd_per_order: float) -> None:
        if usd_per_order < 0:
            raise ValueError("usd_per_order must be non-negative")
        self._usd_per_order = round_money(usd_per_order)

    def compute(self, shares: int, notional_usd: float) -> float:
        return self._usd_per_order


class PerShareCommission:
    """
    Per-share commission with an optional per-order minimum
    (``model: per_share``).
    """

    model_id = "per_share"

    def __init__(self, usd_per_share: float, minimum_usd_per_order: float = 0.0) -> None:
        if usd_per_share < 0:
            raise ValueError("usd_per_share must be non-negative")
        if minimum_usd_per_order < 0:
            raise ValueError("minimum_usd_per_order must be non-negative")
        self._usd_per_share = usd_per_share
        self._minimum_usd_per_order = round_money(minimum_usd_per_order)

    def compute(self, shares: int, notional_usd: float) -> float:
        raw = round_money(shares * self._usd_per_share)
        return max(raw, self._minimum_usd_per_order)


class BpsCommission:
    """Commission as a basis-point percentage of trade notional (``model: bps``)."""

    model_id = "bps"

    def __init__(self, bps_of_notional: float) -> None:
        if bps_of_notional < 0:
            raise ValueError("bps_of_notional must be non-negative")
        self._bps_of_notional = bps_of_notional

    def compute(self, shares: int, notional_usd: float) -> float:
        return round_money(_bps_value(self._bps_of_notional, notional_usd))


# ---------------------------------------------------------------------------
# Spread and slippage implementations
# ---------------------------------------------------------------------------


class FixedBpsSpread:
    """
    Synthetic spread (``model: fixed_bps``).

    ``full_spread_bps`` is the total quoted spread; half of it is applied
    adversely once per side (docs/04 §6).
    """

    model_id = "fixed_bps"

    def __init__(self, full_spread_bps: float) -> None:
        if full_spread_bps < 0:
            raise ValueError("full_spread_bps must be non-negative")
        self._half_spread_bps = full_spread_bps / 2.0

    def compute(self, shares: int, notional_usd: float) -> float:
        return round_money(_bps_value(self._half_spread_bps, notional_usd))


class FixedBpsSlippage:
    """Fixed basis-point slippage per side (``model: fixed_bps``)."""

    model_id = "fixed_bps"

    def __init__(self, bps_per_side: float) -> None:
        if bps_per_side < 0:
            raise ValueError("bps_per_side must be non-negative")
        self._bps_per_side = bps_per_side

    def compute(self, shares: int, notional_usd: float) -> float:
        return round_money(_bps_value(self._bps_per_side, notional_usd))


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostDecomposition:
    """Per-fill cost decomposition (docs/04 §6)."""

    base_price: float
    shares: int
    action: Literal["buy", "sell"]
    spread_usd: float
    slippage_usd: float
    commission_usd: float

    @property
    def total_cost_usd(self) -> float:
        return round_money(self.spread_usd + self.slippage_usd + self.commission_usd)

    @property
    def effective_price(self) -> float:
        """
        Informational execution price including all costs as a per-share
        adverse adjustment: buys pay up (+), sells receive less (-).
        """
        per_share_cost = self.total_cost_usd / self.shares
        return self.base_price + (per_share_cost if self.action == "buy" else -per_share_cost)


@dataclass(frozen=True)
class ExecutionCosts:
    """Bundle of the resolved spread, slippage, and commission models."""

    spread: SpreadModel
    slippage: SlippageModel
    commission: CommissionModel

    def decompose(
        self, *, base_price: float, shares: int, action: Literal["buy", "sell"]
    ) -> CostDecomposition:
        """Compute the full cost decomposition for a fill."""
        if base_price <= 0:
            raise ValueError("base_price must be positive")
        if shares <= 0:
            raise ValueError("shares must be positive")
        notional = base_price * shares
        spread_usd = self.spread.compute(shares, notional)
        slippage_usd = self.slippage.compute(shares, notional)
        commission_usd = self.commission.compute(shares, notional)
        return CostDecomposition(
            base_price=base_price,
            shares=shares,
            action=action,
            spread_usd=spread_usd,
            slippage_usd=slippage_usd,
            commission_usd=commission_usd,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_commission(config: CommissionConfig) -> CommissionModel:
    """Build a commission model from its resolved configuration."""
    if config.model == "zero":
        return ZeroCommission()
    if config.model == "fixed_per_order":
        assert config.usd_per_order is not None
        return FixedPerOrderCommission(config.usd_per_order)
    if config.model == "per_share":
        assert config.usd_per_share is not None
        return PerShareCommission(
            usd_per_share=config.usd_per_share,
            minimum_usd_per_order=config.minimum_usd_per_order or 0.0,
        )
    if config.model == "bps":
        assert config.bps_of_notional is not None
        return BpsCommission(config.bps_of_notional)
    raise ValueError(f"unknown commission model: {config.model}")


def build_spread(config: SpreadConfig) -> SpreadModel:
    """Build a spread model from its resolved configuration."""
    if config.model == "fixed_bps":
        return FixedBpsSpread(config.full_spread_bps)
    raise ValueError(f"unknown spread model: {config.model}")


def build_slippage(config: SlippageConfig) -> SlippageModel:
    """Build a slippage model from its resolved configuration."""
    if config.model == "fixed_bps":
        return FixedBpsSlippage(config.bps_per_side)
    raise ValueError(f"unknown slippage model: {config.model}")


def build_execution_costs(config: ExecutionConfig) -> ExecutionCosts:
    """Build the full execution-cost bundle from the resolved execution config."""
    return ExecutionCosts(
        spread=build_spread(config.spread),
        slippage=build_slippage(config.slippage),
        commission=build_commission(config.commission),
    )
