"""Tests for the T410 execution cost models and decomposition invariants."""

import pytest
from pydantic import ValidationError

from edgeback.config.models import (
    CommissionConfig,
    ExecutionConfig,
    SlippageConfig,
    SpreadConfig,
    VolumeParticipationConfig,
)
from edgeback.execution import (
    BpsCommission,
    CostDecomposition,
    ExecutionCosts,
    FixedBpsSlippage,
    FixedBpsSpread,
    FixedPerOrderCommission,
    PerShareCommission,
    ZeroCommission,
    build_commission,
    build_execution_costs,
)
from edgeback.portfolio.accounting import round_money

SHARES = 100
PRICE = 100.0
NOTIONAL = SHARES * PRICE  # 10_000.0


def execution_config(
    *,
    commission: CommissionConfig,
    spread_bps: float = 2.0,
    slippage_bps: float = 1.0,
) -> ExecutionConfig:
    return ExecutionConfig(
        spread=SpreadConfig(model="fixed_bps", full_spread_bps=spread_bps),
        slippage=SlippageConfig(model="fixed_bps", bps_per_side=slippage_bps),
        commission=commission,
        volume_participation=VolumeParticipationConfig(
            max_pct_of_bar_volume=1.0, on_exceed="reject"
        ),
    )


# ---------------------------------------------------------------------------
# Commission models
# ---------------------------------------------------------------------------


def test_zero_commission() -> None:
    model = ZeroCommission()
    assert model.model_id == "zero"
    assert model.compute(SHARES, NOTIONAL) == 0.0


def test_fixed_per_order_commission() -> None:
    model = FixedPerOrderCommission(usd_per_order=1.25)
    assert model.compute(SHARES, NOTIONAL) == 1.25
    assert model.compute(1, 1.0) == 1.25  # independent of size


def test_per_share_commission_without_minimum() -> None:
    model = PerShareCommission(usd_per_share=0.005)
    assert model.compute(100, 10_000.0) == 0.5


def test_per_share_commission_with_minimum() -> None:
    model = PerShareCommission(usd_per_share=0.005, minimum_usd_per_order=1.0)
    # 5 shares * 0.005 = 0.025 -> floored to the 1.00 minimum.
    assert model.compute(5, 500.0) == 1.0
    # 400 shares * 0.005 = 2.00 exceeds the minimum.
    assert model.compute(400, 40_000.0) == 2.0


def test_bps_commission() -> None:
    model = BpsCommission(bps_of_notional=10.0)
    # 10 bps = 0.1% of 10 000 = 10.00.
    assert model.compute(SHARES, NOTIONAL) == 10.0
    # 1 bps of 10 000 = 1.00.
    assert BpsCommission(1.0).compute(SHARES, NOTIONAL) == 1.0


def test_negative_params_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        FixedPerOrderCommission(-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        PerShareCommission(-0.1)
    with pytest.raises(ValueError, match="non-negative"):
        PerShareCommission(0.1, minimum_usd_per_order=-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        BpsCommission(-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        FixedBpsSpread(-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        FixedBpsSlippage(-1.0)


# ---------------------------------------------------------------------------
# Spread and slippage
# ---------------------------------------------------------------------------


def test_fixed_bps_spread_half_side() -> None:
    model = FixedBpsSpread(full_spread_bps=2.0)
    # Half of the full spread is applied adversely per side: 1 bps of 10 000.
    assert model.compute(SHARES, NOTIONAL) == 1.0
    assert model.model_id == "fixed_bps"


def test_fixed_bps_slippage() -> None:
    model = FixedBpsSlippage(bps_per_side=1.0)
    assert model.compute(SHARES, NOTIONAL) == 1.0
    assert model.model_id == "fixed_bps"


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


def test_commission_config_requires_model_params() -> None:
    with pytest.raises(ValidationError, match="per_share commission requires usd_per_share"):
        CommissionConfig(model="per_share")
    with pytest.raises(ValidationError, match="bps commission requires bps_of_notional"):
        CommissionConfig(model="bps")
    with pytest.raises(ValidationError, match="fixed_per_order commission requires usd_per_order"):
        CommissionConfig(model="fixed_per_order")
    # Valid selected models construct fine.
    CommissionConfig(model="zero")
    CommissionConfig(model="per_share", usd_per_share=0.005)
    CommissionConfig(model="fixed_per_order", usd_per_order=1.0)
    CommissionConfig(model="bps", bps_of_notional=5.0)


def test_spread_model_literal() -> None:
    with pytest.raises(ValidationError):
        SpreadConfig(model="dynamic", full_spread_bps=2.0)  # type: ignore[arg-type]


def test_slippage_model_literal() -> None:
    with pytest.raises(ValidationError):
        SlippageConfig(model="dynamic", bps_per_side=1.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Factory and decomposition
# ---------------------------------------------------------------------------


def test_build_commission_models() -> None:
    assert build_commission(CommissionConfig(model="zero")).model_id == "zero"
    model = build_commission(CommissionConfig(model="per_share", usd_per_share=0.005))
    assert model.model_id == "per_share"
    assert model.compute(100, 10_000.0) == 0.5


def test_build_execution_costs_and_decompose() -> None:
    """Mirrors the resolved execution block in configs/example_backtest.yaml."""
    costs = build_execution_costs(
        execution_config(
            commission=CommissionConfig(
                model="per_share", usd_per_share=0.005, minimum_usd_per_order=0.0
            ),
            spread_bps=2.0,
            slippage_bps=1.0,
        )
    )
    assert isinstance(costs, ExecutionCosts)
    deco = costs.decompose(base_price=PRICE, shares=SHARES, action="buy")
    assert isinstance(deco, CostDecomposition)
    assert deco.base_price == 100.0
    assert deco.shares == 100
    assert deco.action == "buy"
    # Half of 2 bps full spread on 10 000 = 1.00; slippage 1 bps = 1.00.
    assert deco.spread_usd == 1.0
    assert deco.slippage_usd == 1.0
    assert deco.commission_usd == 0.5
    assert deco.total_cost_usd == 2.5
    # Buy pays adverse: 100 + 2.5/100 = 100.025.
    assert deco.effective_price == 100.025


def test_effective_price_direction() -> None:
    costs = build_execution_costs(
        execution_config(
            commission=CommissionConfig(model="zero"),
            spread_bps=2.0,
            slippage_bps=0.0,
        )
    )
    buy = costs.decompose(base_price=100.0, shares=100, action="buy")
    sell = costs.decompose(base_price=100.0, shares=100, action="sell")
    # Buy pays the half-spread up, sell receives less than the base price.
    assert buy.effective_price == 100.01
    assert sell.effective_price == 99.99


def test_round_trip_cash_consistency() -> None:
    """A flat buy-then-sell round trip's cash change equals -(sum of both sides' costs)."""
    costs = build_execution_costs(
        execution_config(
            commission=CommissionConfig(
                model="per_share", usd_per_share=0.005, minimum_usd_per_order=0.0
            ),
            spread_bps=2.0,
            slippage_bps=1.0,
        )
    )
    buy = costs.decompose(base_price=100.0, shares=100, action="buy")
    sell = costs.decompose(base_price=100.0, shares=100, action="sell")
    # Buy pays 100*100 + 2.5; sell receives 100*100 - 2.5 -> net cash -5.0,
    # i.e. negative the sum of both sides' costs.
    cash_change = round_money(-100 * 100.0 - buy.total_cost_usd) + round_money(
        +100 * 100.0 - sell.total_cost_usd
    )
    assert cash_change == round_money(-(buy.total_cost_usd + sell.total_cost_usd))


def test_decompose_validation() -> None:
    costs = build_execution_costs(execution_config(commission=CommissionConfig(model="zero")))
    with pytest.raises(ValueError, match="base_price"):
        costs.decompose(base_price=0.0, shares=1, action="buy")
    with pytest.raises(ValueError, match="shares"):
        costs.decompose(base_price=100.0, shares=0, action="buy")


def test_zero_cost_decomposition() -> None:
    """A zero-cost profile decomposes fully to zeros."""
    costs = build_execution_costs(
        execution_config(
            commission=CommissionConfig(model="zero"), spread_bps=0.0, slippage_bps=0.0
        )
    )
    deco = costs.decompose(base_price=100.0, shares=100, action="sell")
    assert deco.spread_usd == 0.0
    assert deco.slippage_usd == 0.0
    assert deco.commission_usd == 0.0
    assert deco.total_cost_usd == 0.0
    assert deco.effective_price == 100.0
